// Probe tests for ju26-issue-2234, written by the review team (not part of the branch).
// Copied into tests/MessagePack.SourceGenerator.Tests on a worktree of base and of the branch by
// review/proof/run_2234_probes.py. They do not assert; they write what the real code does to
// the JSON file named by the PROBE_OUT environment variable, and the runner compares.
//
// 1. Scenarios: real analyzer (MsgPack00xMessagePackAnalyzer) on small sources, all diagnostics recorded,
//    analyzer exceptions show up as AD0001.
// 2. Exhaustive: every list of 1..4 keyed members (kind Prop/Field, key 0, 1, "a", "b", null), properties
//    before fields as the C# visits them, run through the real TypeCollector.Collect. Records exception,
//    IsIntKey, the key map of the generated model, and the Dup/Mix/BothNull reports in order.
using System.Text;
using System.Text.Json;
using MessagePack.SourceGenerator.Analyzers;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.Diagnostics;
using Microsoft.CodeAnalysis.Testing;

public class Probe2234Tests
{
    private static readonly string[] KeyChoices = { "0", "1", "\"a\"", "\"b\"", "null" };

    private static async Task<ImmutableArray<MetadataReference>> RefsAsync()
    {
        var refs = await ReferenceAssemblies.Net.Net80.ResolveAsync(LanguageNames.CSharp, CancellationToken.None);
        return refs.Add(MetadataReference.CreateFromFile(typeof(MessagePack.MessagePackObjectAttribute).Assembly.Location));
    }

    private static CSharpCompilation Compile(string src, ImmutableArray<MetadataReference> refs)
        => CSharpCompilation.Create("Probe", new[] { CSharpSyntaxTree.ParseText(src) }, refs, new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary));

    private static void Write(string name, object value)
    {
        string dir = Environment.GetEnvironmentVariable("PROBE_OUT") ?? Path.GetTempPath();
        Directory.CreateDirectory(dir);
        File.WriteAllText(Path.Combine(dir, name), JsonSerializer.Serialize(value, new JsonSerializerOptions { WriteIndented = true }));
    }

    private static readonly Dictionary<string, string> Scenarios = new()
    {
        // (a) the new `continue` skips collecting the member's type. Member2 has a mixed key and a type that is not serializable.
        ["a_string_then_int_member_type_unserializable"] = @"using MessagePack;
public class Other { }
[MessagePackObject]
public class Foo
{
    [Key(""a"")] public int Member1 { get; set; }
    [Key(1)] public Other Member2 { get; set; }
}",
        ["a_string_then_int_member_type_unserializable_suppressed"] = @"using MessagePack;
public class Other { }
[MessagePackObject(SuppressSourceGeneration = true)]
public class Foo
{
    [Key(""a"")] public int Member1 { get; set; }
    [Key(1)] public Other Member2 { get; set; }
}",
        ["a_int_then_string_member_type_unserializable"] = @"using MessagePack;
public class Other { }
[MessagePackObject]
public class Foo
{
    [Key(0)] public int Member1 { get; set; }
    [Key(""b"")] public Other Member2 { get; set; }
}",
        // control: same unserializable type on a member with a valid key
        ["a_control_valid_key_member_type_unserializable"] = @"using MessagePack;
public class Other { }
[MessagePackObject]
public class Foo
{
    [Key(0)] public int Member1 { get; set; }
    [Key(1)] public Other Member2 { get; set; }
}",
        // (b) two members share a key: which diagnostics?
        ["b_duplicate_int_key_different_types"] = @"using MessagePack;
[MessagePackObject]
public class Foo
{
    [Key(0)] public int Member1 { get; set; }
    [Key(0)] public string Member2 { get; set; }
}",
        ["b_duplicate_string_key_fields"] = @"using MessagePack;
[MessagePackObject]
public class Foo
{
    [Key(""a"")] public int Member1;
    [Key(""a"")] public string Member2;
}",
        ["b_duplicate_int_key_property_and_field"] = @"using MessagePack;
[MessagePackObject]
public class Foo
{
    [Key(0)] public int Member1 { get; set; }
    [Key(0)] public int Member2;
}",
        // null key as the first keyed member: property vs field (model predicts the field crashes)
        ["null_key_first_field"] = @"using MessagePack;
[MessagePackObject]
public class Foo
{
    [Key(null)] public int Member1;
}",
        ["null_key_first_field_suppressed"] = @"using MessagePack;
[MessagePackObject(SuppressSourceGeneration = true)]
public class Foo
{
    [Key(null)] public int Member1;
}",
        ["null_key_first_property"] = @"using MessagePack;
[MessagePackObject]
public class Foo
{
    [Key(null)] public int Member1 { get; set; }
}",
        ["null_key_second_field"] = @"using MessagePack;
[MessagePackObject]
public class Foo
{
    [Key(""a"")] public int Member1;
    [Key(null)] public int Member2;
}",
    };

    [Fact]
    public async Task AnalyzerScenarios()
    {
        var refs = await RefsAsync();
        var results = new Dictionary<string, object>();
        foreach (var (name, src) in Scenarios)
        {
            var comp = Compile(src, refs);
            var compileErrors = comp.GetDiagnostics().Where(d => d.Severity == DiagnosticSeverity.Error).Select(d => d.ToString()).ToArray();
            var cwa = comp.WithAnalyzers(
                ImmutableArray.Create<DiagnosticAnalyzer>(new MsgPack00xMessagePackAnalyzer()),
                new CompilationWithAnalyzersOptions(new Microsoft.CodeAnalysis.Diagnostics.AnalyzerOptions(ImmutableArray<AdditionalText>.Empty), null, concurrentAnalysis: false, logAnalyzerExecutionTime: false));
            var diags = await cwa.GetAnalyzerDiagnosticsAsync();
            results[name] = new
            {
                source = src,
                compile_errors = compileErrors,
                diagnostics = diags.OrderBy(d => d.Location.SourceSpan.Start).Select(d => new
                {
                    id = d.Id,
                    line = d.Location.IsInSource ? d.Location.GetLineSpan().StartLinePosition.Line + 1 : 0,
                    message = d.GetMessage().Split('\n')[0],
                }).ToArray(),
            };
        }

        Write("scenarios.json", results);
    }

    [Fact]
    public async Task ExhaustiveKeyCollection()
    {
        var refs = await RefsAsync();
        var rows = new List<object>();
        var options = new MessagePack.SourceGenerator.CodeAnalysis.AnalyzerOptions();
        for (int n = 1; n <= 4; n++)
        {
            foreach (var input in Enumerate(n))
            {
                rows.Add(RunOne(input, refs, options));
            }
        }

        Write("exhaustive.json", rows);
    }

    private static IEnumerable<(bool IsField, int KeyChoice)[]> Enumerate(int n)
    {
        int total = 1;
        for (int i = 0; i < n; i++)
        {
            total *= 10;
        }

        for (int code = 0; code < total; code++)
        {
            var arr = new (bool, int)[n];
            int c = code;
            for (int i = 0; i < n; i++)
            {
                int d = c % 10;
                c /= 10;
                arr[i] = (d >= 5, d % 5);
            }

            bool sorted = true;
            for (int i = 1; i < n; i++)
            {
                if (arr[i - 1].Item1 && !arr[i].Item1)
                {
                    sorted = false; // a field before a property: the C# cannot visit members in that order
                }
            }

            if (sorted)
            {
                yield return arr;
            }
        }
    }

    private static object RunOne((bool IsField, int KeyChoice)[] input, ImmutableArray<MetadataReference> refs, MessagePack.SourceGenerator.CodeAnalysis.AnalyzerOptions options)
    {
        const int firstMemberLine = 5; // 1-based line of member 0 in the source below
        var sb = new StringBuilder();
        sb.Append("using MessagePack;\n[MessagePackObject]\npublic class Foo\n{\n");
        for (int i = 0; i < input.Length; i++)
        {
            string key = KeyChoices[input[i].KeyChoice];
            sb.Append(input[i].IsField ? $"    [Key({key})] public int M{i};\n" : $"    [Key({key})] public int M{i} {{ get; set; }}\n");
        }

        sb.Append("}\n");
        var comp = Compile(sb.ToString(), refs);
        var reports = new List<object>();
        var other = new List<string>();
        Action<Diagnostic> report = d =>
        {
            int idx = d.Location.IsInSource ? d.Location.GetLineSpan().StartLinePosition.Line + 1 - firstMemberLine : -1;
            string? tag = ReferenceEquals(d.Descriptor, MsgPack00xMessagePackAnalyzer.KeysMustBeUnique) ? "Dup"
                : ReferenceEquals(d.Descriptor, MsgPack00xMessagePackAnalyzer.DoNotMixStringAndIntKeys) ? "Mix"
                : ReferenceEquals(d.Descriptor, MsgPack00xMessagePackAnalyzer.BothStringAndIntKeyAreNull) ? "BothNull"
                : null;
            if (tag is null)
            {
                other.Add($"{d.Id}@{idx}");
            }
            else
            {
                reports.Add(new object[] { tag, idx });
            }
        };

        string? exception = null;
        bool? isInt = null;
        var map = new SortedDictionary<string, int>(StringComparer.Ordinal);
        try
        {
            if (!ReferenceSymbols.TryCreate(comp, out ReferenceSymbols? rs))
            {
                throw new InvalidOperationException("ReferenceSymbols.TryCreate failed");
            }

            var type = comp.GetTypeByMetadataName("Foo")!;
            FullModel? model = TypeCollector.Collect(comp, options, rs, report, type, CancellationToken.None);
            var info = model?.ObjectInfos.SingleOrDefault(); // members are all int, so Foo is the only object collected
            if (info is not null)
            {
                isInt = info.IsIntKey;
                foreach (var m in info.Members)
                {
                    int idx = int.Parse(m.Name.Substring(1));
                    map[info.IsIntKey ? "i:" + m.IntKey : "s:" + m.StringKey] = idx;
                }
            }
        }
        catch (Exception ex)
        {
            exception = ex.GetType().FullName;
        }

        return new
        {
            input = input.Select(x => new object[] { x.IsField ? "Field" : "Prop", KeyChoices[x.KeyChoice] }).ToArray(),
            exception,
            is_int = isInt,
            map,
            reports,
            other,
        };
    }
}
