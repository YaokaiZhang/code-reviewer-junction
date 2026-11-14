// Isolation harness: run one side's (base or branch) MessagePack source generators and analyzers over a set of
// recorded inputs and write a normalized JSON per input. review/scripts/isolation_check.py runs it once per side
// and diffs the outputs.
//
// Usage:
//   IsolationHarness --generator <MessagePack.SourceGenerator.dll> --inputs <dir with *.json> --out <dir>
//                    [--ref-override MessagePack.dll=<path>] [--ref-override MessagePack.Annotations.dll=<path>]
//
// Input JSON (written by CorpusDump.cs for test inputs, or by isolation_check.py for real projects):
//   { id, documents: [{name, text} | {name, path}], parse_options: {language_version, preprocessor_symbols, documentation_mode},
//     compilation_options: {output_kind, nullable, allow_unsafe, warning_level, general_diagnostic_option,
//     specific_diagnostic_options, check_overflow, optimization}, metadata_references: [paths],
//     additional_files: [{name, text}], project_references: [ same shape, compiled first ], root?: path prefix to strip }
using System.Collections.Immutable;
using System.Globalization;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.Diagnostics;
using Microsoft.CodeAnalysis.Text;

internal static class Program
{
    private static readonly Dictionary<string, MetadataReference> RefCache = new(StringComparer.Ordinal);

    private static int Main(string[] args)
    {
        string? generatorPath = null, inputs = null, outDir = null;
        var overrides = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        for (int i = 0; i < args.Length; i++)
        {
            switch (args[i])
            {
                case "--generator": generatorPath = args[++i]; break;
                case "--inputs": inputs = args[++i]; break;
                case "--out": outDir = args[++i]; break;
                case "--ref-override":
                    var kv = args[++i].Split('=', 2);
                    overrides[kv[0]] = kv[1];
                    break;
                default:
                    Console.Error.WriteLine($"unknown argument {args[i]}");
                    return 2;
            }
        }

        if (generatorPath is null || inputs is null || outDir is null)
        {
            Console.Error.WriteLine("usage: --generator DLL --inputs DIR --out DIR [--ref-override NAME=PATH]");
            return 2;
        }

        Directory.CreateDirectory(outDir);
        Assembly genAsm = Assembly.LoadFrom(Path.GetFullPath(generatorPath));
        Type[] types;
        try
        {
            types = genAsm.GetTypes();
        }
        catch (ReflectionTypeLoadException ex)
        {
            types = ex.Types.Where(t => t is not null).ToArray()!;
        }

        // Everything a user's C# build gets from the package: all [Generator] types and all C# analyzers.
        var generatorTypes = types.Where(t => !t.IsAbstract && t.GetCustomAttributes<GeneratorAttribute>().Any()
                                              && (typeof(IIncrementalGenerator).IsAssignableFrom(t) || typeof(ISourceGenerator).IsAssignableFrom(t)))
                                  .OrderBy(t => t.FullName).ToArray();
        var analyzerTypes = types.Where(t => !t.IsAbstract && typeof(DiagnosticAnalyzer).IsAssignableFrom(t)
                                             && t.GetCustomAttributes<DiagnosticAnalyzerAttribute>().Any(a => a.Languages.Contains(LanguageNames.CSharp)))
                                 .OrderBy(t => t.FullName).ToArray();
        Console.Error.WriteLine($"[harness] {genAsm.GetName().Name}: generators {string.Join(", ", generatorTypes.Select(t => t.Name))}; analyzers {string.Join(", ", analyzerTypes.Select(t => t.Name))}; Roslyn {typeof(Compilation).Assembly.GetName().Version}");

        var files = Directory.GetFiles(inputs, "*.json").OrderBy(f => f, StringComparer.Ordinal).ToArray();
        int ok = 0, crashed = 0;
        foreach (string file in files)
        {
            var input = JsonNode.Parse(File.ReadAllText(file))!.AsObject();
            string id = (string?)input["id"] ?? Path.GetFileNameWithoutExtension(file);
            JsonObject result;
            var sw = System.Diagnostics.Stopwatch.StartNew();
            try
            {
                result = RunOne(input, generatorTypes, analyzerTypes, overrides);
                ok++;
            }
            catch (Exception ex)
            {
                result = new JsonObject { ["status"] = "crash", ["error"] = ex.GetType().FullName + ": " + ex.Message, ["stack"] = ex.StackTrace };
                crashed++;
            }

            result["id"] = id;
            result["seconds"] = Math.Round(sw.Elapsed.TotalSeconds, 2);
            File.WriteAllText(Path.Combine(outDir, id + ".json"), result.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
        }

        Console.Error.WriteLine($"[harness] {files.Length} inputs: {ok} ran, {crashed} harness crashes");
        return 0;
    }

    private static JsonObject RunOne(JsonObject input, Type[] generatorTypes, Type[] analyzerTypes, Dictionary<string, string> overrides)
    {
        string root = (string?)input["root"] ?? string.Empty;
        var result = new JsonObject { ["status"] = "ok" };
        var generated = new JsonObject();
        var genDiags = new List<Diagnostic>();
        var genExceptions = new JsonArray();

        // Referenced projects (tests that use AdditionalProjects): compile first, run the generator on them too if
        // the test framework gave them analyzers, and reference them as compilations.
        var extraRefs = new List<MetadataReference>();
        foreach (var pr in input["project_references"]?.AsArray() ?? new JsonArray())
        {
            var prObj = pr!.AsObject();
            var (prComp, prParse) = CreateCompilation(prObj, overrides, extraRefs: new());
            string prName = (string?)prObj["assembly_name"] ?? "ref";
            if ((bool?)prObj["has_analyzer_references"] == true)
            {
                prComp = RunGenerators(prComp, prParse, prObj, generatorTypes, generated, genDiags, genExceptions, prName + "/");
            }

            extraRefs.Add(prComp.ToMetadataReference());
        }

        var (compilation, parseOptions) = CreateCompilation(input, overrides, extraRefs);
        var output = RunGenerators(compilation, parseOptions, input, generatorTypes, generated, genDiags, genExceptions, string.Empty);

        var analyzers = analyzerTypes.Select(t => (DiagnosticAnalyzer)Activator.CreateInstance(t)!).ToImmutableArray();
        var additional = AdditionalTexts(input);
        var cwa = output.WithAnalyzers(analyzers, new CompilationWithAnalyzersOptions(
            new AnalyzerOptions(additional), onAnalyzerException: null, concurrentAnalysis: false, logAnalyzerExecutionTime: false, reportSuppressedDiagnostics: false));
        var analyzerDiags = cwa.GetAnalyzerDiagnosticsAsync(CancellationToken.None).GetAwaiter().GetResult();
        var compilerDiags = output.GetDiagnostics().Where(d => d.Severity >= DiagnosticSeverity.Warning).ToList();

        result["generated"] = generated;
        result["generator_exceptions"] = genExceptions;
        result["generator_diagnostics"] = Diags(genDiags, root);
        result["analyzer_diagnostics"] = Diags(analyzerDiags, root);
        result["compiler_diagnostics"] = Diags(compilerDiags, root);
        result["compiler_errors"] = compilerDiags.Count(d => d.Severity == DiagnosticSeverity.Error);
        result["user_source_errors_before_generation"] = compilation.GetDiagnostics().Count(d => d.Severity == DiagnosticSeverity.Error);
        return result;
    }

    private static Compilation RunGenerators(Compilation compilation, CSharpParseOptions parseOptions, JsonObject input, Type[] generatorTypes,
        JsonObject generated, List<Diagnostic> genDiags, JsonArray genExceptions, string prefix)
    {
        var generators = generatorTypes.Select(t =>
        {
            object g = Activator.CreateInstance(t)!;
            return g is IIncrementalGenerator ig ? ig.AsSourceGenerator() : (ISourceGenerator)g;
        }).ToList();
        GeneratorDriver driver = CSharpGeneratorDriver.Create(generators, AdditionalTexts(input), parseOptions);
        driver = driver.RunGeneratorsAndUpdateCompilation(compilation, out var output, out var diags);
        genDiags.AddRange(diags);
        var run = driver.GetRunResult();
        foreach (var r in run.Results)
        {
            if (r.Exception is not null)
            {
                genExceptions.Add(JsonValue.Create($"{prefix}{r.Generator.GetGeneratorType().Name}: {r.Exception.GetType().FullName}: {r.Exception.Message}"));
            }

            foreach (var s in r.GeneratedSources.OrderBy(s => s.HintName, StringComparer.Ordinal))
            {
                generated[$"{prefix}{r.Generator.GetGeneratorType().Name}/{s.HintName}"] = s.SourceText.ToString().Replace("\r\n", "\n");
            }
        }

        return output;
    }

    private static ImmutableArray<AdditionalText> AdditionalTexts(JsonObject input)
        => (input["additional_files"]?.AsArray() ?? new JsonArray())
            .Select(a => (AdditionalText)new InMemoryAdditionalText((string)a!["name"]!, (string)a["text"]!)).ToImmutableArray();

    private static (Compilation, CSharpParseOptions) CreateCompilation(JsonObject input, Dictionary<string, string> overrides, List<MetadataReference> extraRefs)
    {
        var po = input["parse_options"]?.AsObject();
        var langVersion = Enum.Parse<LanguageVersion>((string?)po?["language_version"] ?? "Default");
        var symbols = po?["preprocessor_symbols"]?.AsArray().Select(s => (string)s!).ToArray() ?? Array.Empty<string>();
        var docMode = Enum.Parse<DocumentationMode>((string?)po?["documentation_mode"] ?? "Parse");
        var parseOptions = new CSharpParseOptions(langVersion, docMode, SourceCodeKind.Regular, symbols);

        var trees = new List<SyntaxTree>();
        foreach (var d in input["documents"]!.AsArray())
        {
            string name = (string)d!["name"]!;
            string text = d["text"] is JsonNode t ? (string)t! : File.ReadAllText((string)d["path"]!);
            trees.Add(CSharpSyntaxTree.ParseText(SourceText.From(text, System.Text.Encoding.UTF8), parseOptions, path: name));
        }

        var co = input["compilation_options"]?.AsObject();
        var options = new CSharpCompilationOptions(Enum.Parse<OutputKind>((string?)co?["output_kind"] ?? "DynamicallyLinkedLibrary"))
            .WithNullableContextOptions(Enum.Parse<NullableContextOptions>((string?)co?["nullable"] ?? "Disable"))
            .WithAllowUnsafe((bool?)co?["allow_unsafe"] ?? false)
            .WithWarningLevel((int?)co?["warning_level"] ?? 4)
            .WithGeneralDiagnosticOption(Enum.Parse<ReportDiagnostic>((string?)co?["general_diagnostic_option"] ?? "Default"))
            .WithOverflowChecks((bool?)co?["check_overflow"] ?? false)
            .WithOptimizationLevel(Enum.Parse<OptimizationLevel>((string?)co?["optimization"] ?? "Debug"))
            .WithSpecificDiagnosticOptions((co?["specific_diagnostic_options"]?.AsObject() ?? new JsonObject())
                .Select(kv => new KeyValuePair<string, ReportDiagnostic>(kv.Key, Enum.Parse<ReportDiagnostic>((string)kv.Value!))));

        var refs = new List<MetadataReference>();
        foreach (var r in input["metadata_references"]!.AsArray())
        {
            string path = (string)r!;
            if (overrides.TryGetValue(Path.GetFileName(path), out var replacement))
            {
                path = replacement;
            }

            if (!RefCache.TryGetValue(path, out var mr))
            {
                mr = path.StartsWith("mdblob:", StringComparison.Ordinal) ? FromMetadataBlob(path.Substring(7)) : MetadataReference.CreateFromFile(path);
                RefCache[path] = mr;
            }

            refs.Add(mr);
        }

        refs.AddRange(extraRefs);
        var compilation = CSharpCompilation.Create((string?)input["assembly_name"] ?? "TestProject", trees, refs, options);
        return (compilation, parseOptions);
    }

    // Metadata-only reference saved by CorpusDump for an assembly a test compiled in memory. The memory is
    // deliberately never freed: the harness is a short-lived process.
    private static MetadataReference FromMetadataBlob(string file)
    {
        byte[] bytes = File.ReadAllBytes(file);
        IntPtr mem = System.Runtime.InteropServices.Marshal.AllocHGlobal(bytes.Length);
        System.Runtime.InteropServices.Marshal.Copy(bytes, 0, mem, bytes.Length);
        return AssemblyMetadata.Create(ModuleMetadata.CreateFromMetadata(mem, bytes.Length)).GetReference(filePath: file);
    }

    private static JsonArray Diags(IEnumerable<Diagnostic> diags, string root)
    {
        var rows = diags.Select(d =>
        {
            string loc = "(none)";
            if (d.Location.IsInSource)
            {
                var span = d.Location.GetLineSpan();
                string path = span.Path ?? string.Empty;
                if (root.Length > 0 && path.StartsWith(root, StringComparison.Ordinal))
                {
                    path = path.Substring(root.Length);
                }

                // Generated trees: keep the hint name only (the generator folder prefix is noise).
                if (path.StartsWith("MessagePack.SourceGenerator/", StringComparison.Ordinal))
                {
                    path = "generated:" + path.Substring(path.LastIndexOf('/') + 1);
                }

                loc = $"{path}:{span.StartLinePosition.Line + 1}";
            }
            else if (d.Location.Kind != LocationKind.None)
            {
                loc = "(" + d.Location.Kind + ")";
            }

            string message = d.GetMessage(CultureInfo.InvariantCulture).Replace("\r\n", "\n");
            int nl = message.IndexOf('\n');
            if (nl >= 0)
            {
                message = message.Substring(0, nl);
            }

            return (id: d.Id, sev: d.Severity.ToString(), loc, message);
        })
        .OrderBy(x => x.loc, StringComparer.Ordinal).ThenBy(x => x.id, StringComparer.Ordinal).ThenBy(x => x.message, StringComparer.Ordinal);
        var arr = new JsonArray();
        foreach (var r in rows)
        {
            arr.Add(new JsonObject { ["id"] = r.id, ["severity"] = r.sev, ["location"] = r.loc, ["message"] = r.message });
        }

        return arr;
    }

    private sealed class InMemoryAdditionalText(string path, string text) : AdditionalText
    {
        private readonly SourceText source = SourceText.From(text);

        public override string Path => path;

        public override SourceText GetText(CancellationToken cancellationToken = default) => this.source;
    }
}
