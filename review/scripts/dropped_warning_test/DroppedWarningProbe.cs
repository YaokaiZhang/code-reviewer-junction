// Probe for review of ju26-issue-2283. Copied into tests/MessagePack.SourceGenerator.Tests/ by run.py.
// Runs MsgPack00xMessagePackAnalyzer on small consumer projects that use a closed generic type
// defined in another assembly, and writes every analyzer diagnostic (or exception) to JSON.
// It asserts nothing: run.py compares base and branch.

using System.Text.Json;
using MessagePack.SourceGenerator.Analyzers;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.Diagnostics;
using Microsoft.CodeAnalysis.Testing;

public class DroppedWarningProbe
{
    private const string LibBox = """
using MessagePack;
namespace Lib
{
    [MessagePackObject]
    public class Box<T>
    {
        [Key(0)]
        public T Content { get; set; }
    }
}
""";

    private const string AppPlainInBox = """
using MessagePack;
namespace App
{
    // Not attributed: the consumer's own mistake.
    public class Plain { public int X { get; set; } }

    [MessagePackObject]
    public class Holder
    {
        [Key(0)]
        public Lib.Box<Plain> Value { get; set; }
    }

    [GeneratedMessagePackResolver]
    partial class AppResolver { }
}
""";

    private const string LibDup = """
using MessagePack;
namespace Lib
{
    [MessagePackObject]
    public class Dup<T>
    {
        [Key(0)]
        public int A { get; set; }

        [Key(0)]
        public int B { get; set; }
    }
}
""";

    private const string AppUsesDup = """
using MessagePack;
namespace App
{
    [MessagePackObject]
    public class Holder
    {
        [Key(0)]
        public Lib.Dup<int> Value { get; set; }
    }

    [GeneratedMessagePackResolver]
    partial class AppResolver { }
}
""";

    private const string LibUnkeyed = """
using MessagePack;
namespace Lib
{
    [MessagePackObject]
    public struct MyGenericStruct<T>
    {
        [Key(0)]
        public string Key { get; set; }

        public int Unkeyed { get; set; }
    }
}
""";

    private const string AppUsesUnkeyed = """
using MessagePack;
namespace App
{
    [MessagePackObject]
    public class Holder
    {
        [Key(0)]
        public Lib.MyGenericStruct<int> Value { get; set; }
    }

    [GeneratedMessagePackResolver]
    partial class AppResolver { }
}
""";

    [Fact]
    public async Task Probe()
    {
        string? outPath = Environment.GetEnvironmentVariable("DROPPED_WARNING_OUT");
        var cases = new List<object>();

        // Control: same shape, Box<T> declared in the consumer's own source.
        cases.Add(await RunCaseAsync("control_box_in_same_project", null, LibBox + "\n" + AppPlainInBox, asImage: true));

        cases.Add(await RunCaseAsync("unattributed_consumer_type_inside_metadata_generic", LibBox, AppPlainInBox, asImage: true));
        cases.Add(await RunCaseAsync("unattributed_consumer_type_inside_project_reference_generic", LibBox, AppPlainInBox, asImage: false));
        cases.Add(await RunCaseAsync("duplicate_keys_in_metadata_generic", LibDup, AppUsesDup, asImage: true));
        cases.Add(await RunCaseAsync("duplicate_keys_in_project_reference_generic", LibDup, AppUsesDup, asImage: false));
        cases.Add(await RunCaseAsync("unkeyed_member_in_metadata_generic", LibUnkeyed, AppUsesUnkeyed, asImage: true));

        string json = JsonSerializer.Serialize(cases, new JsonSerializerOptions { WriteIndented = true });
        if (outPath is not null)
        {
            File.WriteAllText(outPath, json);
        }
    }

    private static async Task<object> RunCaseAsync(string name, string? libSource, string appSource, bool asImage)
    {
        ImmutableArray<MetadataReference> fx = await ReferenceAssemblies.Net.Net80.ResolveAsync(LanguageNames.CSharp, CancellationToken.None);
        IEnumerable<MetadataReference> refs = fx.Concat(ReferencesHelper.GetReferences(ReferencesSet.MessagePack));
        var parse = CSharpParseOptions.Default.WithLanguageVersion(LanguageVersion.CSharp7_3);
        var opts = new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary);

        string libReferenceKind = "none";
        if (libSource is not null)
        {
            var lib = CSharpCompilation.Create("Lib", new[] { CSharpSyntaxTree.ParseText(libSource, parse, path: "Lib.cs") }, refs, opts);
            MetadataReference libRef;
            if (asImage)
            {
                using var ms = new MemoryStream();
                var emit = lib.Emit(ms);
                if (!emit.Success)
                {
                    throw new InvalidOperationException(string.Join("\n", emit.Diagnostics));
                }

                libRef = MetadataReference.CreateFromImage(ms.ToArray());
                libReferenceKind = "metadata image (NuGet / built DLL)";
            }
            else
            {
                libRef = lib.ToMetadataReference();
                libReferenceKind = "compilation reference (project reference in the IDE)";
            }

            refs = refs.Append(libRef);
        }

        var app = CSharpCompilation.Create("App", new[] { CSharpSyntaxTree.ParseText(appSource, parse, path: "App.cs") }, refs, opts);
        var exceptions = new List<string>();
        var cwaOptions = new CompilationWithAnalyzersOptions(
            new Microsoft.CodeAnalysis.Diagnostics.AnalyzerOptions(ImmutableArray<AdditionalText>.Empty),
            (ex, analyzer, diag) => exceptions.Add(ex.GetType().Name + ": " + ex.Message.Split('\n')[0]),
            concurrentAnalysis: false,
            logAnalyzerExecutionTime: false);
        var cwa = app.WithAnalyzers(ImmutableArray.Create<DiagnosticAnalyzer>(new MsgPack00xMessagePackAnalyzer()), cwaOptions);
        ImmutableArray<Diagnostic> diags = await cwa.GetAnalyzerDiagnosticsAsync(CancellationToken.None);

        return new
        {
            name,
            lib_reference = libReferenceKind,
            diagnostics = diags.Select(d => new
            {
                id = d.Id,
                severity = d.Severity.ToString(),
                message = d.GetMessage(System.Globalization.CultureInfo.InvariantCulture).Split('\n')[0],
                location_kind = d.Location.Kind.ToString(),
                location = d.Location.Kind == LocationKind.None ? "none" : d.Location.ToString(),
            }).ToList(),
            analyzer_exceptions = exceptions,
        };
    }
}
