// Added only to a scratch copy of tests/MessagePack.SourceGenerator.Tests by review/scripts/isolation_check.py.
// It records every compilation the existing tests hand to Roslyn (sources after markup processing, parse and
// compilation options, metadata references, referenced test projects) so the isolation harness can replay the
// exact same inputs against the base and branch generator. It does not change what the tests do.
#nullable enable
using System.Diagnostics;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;

internal static class CorpusDump
{
    private static readonly object Gate = new();

    internal static string FindTestName()
    {
        string? fallback = null;
        foreach (StackFrame frame in new StackTrace().GetFrames())
        {
            MethodBase? m = frame.GetMethod();
            Type? t = m?.DeclaringType;
            if (t is null || m is null)
            {
                continue;
            }

            string method = m.Name;
            if (t.Name.StartsWith("<", StringComparison.Ordinal) && t.DeclaringType is not null)
            {
                int close = t.Name.IndexOf('>');
                method = close > 1 ? t.Name.Substring(1, close - 1) : method;
                t = t.DeclaringType;
            }

            if (t.Assembly != typeof(CorpusDump).Assembly || t.Name.Contains("Verifier"))
            {
                continue;
            }

            // Prefer the [Fact]/[Theory] method itself; a helper in the test class is only a fallback.
            bool isTest(MethodInfo x) => x.GetCustomAttributes().Any(a => a.GetType().Name is "FactAttribute" or "TheoryAttribute");
            var all = t.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static);
            if (all.Any(x => x.Name == method && isTest(x)))
            {
                return $"{t.FullName}.{method}";
            }

            if (fallback is null && all.Any(isTest))
            {
                fallback = $"{t.FullName}.{method}";
            }
        }

        return fallback ?? "unknown";
    }

    internal static void Dump(Project project, string testName, string verifier)
    {
        string? dir = Environment.GetEnvironmentVariable("CORPUS_DUMP_DIR");
        if (string.IsNullOrEmpty(dir))
        {
            return;
        }

        var input = DescribeProject(project, includeReferences: true);
        input["verifier"] = verifier;
        string key = Hash(JsonSerializer.Serialize(input));
        input["id"] = key;
        lock (Gate)
        {
            Directory.CreateDirectory(dir);
            string path = Path.Combine(dir, key + ".json");
            if (!File.Exists(path))
            {
                input["tests"] = new List<string> { testName };
                File.WriteAllText(path, JsonSerializer.Serialize(input, new JsonSerializerOptions { WriteIndented = true }));
            }
            else
            {
                // Same input used by several tests (or Theory rows): record the extra test name.
                File.AppendAllText(Path.Combine(dir, key + ".tests"), testName + "\n");
            }
        }
    }

    private static Dictionary<string, object?> DescribeProject(Project project, bool includeReferences)
    {
        var parse = (CSharpParseOptions?)project.ParseOptions;
        var comp = (CSharpCompilationOptions?)project.CompilationOptions;
        var d = new Dictionary<string, object?>
        {
            ["language"] = project.Language,
            ["assembly_name"] = project.AssemblyName,
            ["documents"] = project.Documents.Select(doc => new Dictionary<string, string>
            {
                ["name"] = doc.FilePath ?? doc.Name,
                ["text"] = doc.GetTextAsync().Result.ToString(),
            }).ToList(),
            ["additional_files"] = project.AdditionalDocuments.Select(doc => new Dictionary<string, string>
            {
                ["name"] = doc.FilePath ?? doc.Name,
                ["text"] = doc.GetTextAsync().Result.ToString(),
            }).ToList(),
            ["analyzer_config_files"] = project.AnalyzerConfigDocuments.Select(doc => new Dictionary<string, string>
            {
                ["name"] = doc.FilePath ?? doc.Name,
                ["text"] = doc.GetTextAsync().Result.ToString(),
            }).ToList(),
            ["parse_options"] = parse is null ? null : new Dictionary<string, object?>
            {
                ["language_version"] = parse.SpecifiedLanguageVersion.ToString(),
                ["preprocessor_symbols"] = parse.PreprocessorSymbolNames.ToList(),
                ["documentation_mode"] = parse.DocumentationMode.ToString(),
            },
            ["compilation_options"] = comp is null ? null : new Dictionary<string, object?>
            {
                ["output_kind"] = comp.OutputKind.ToString(),
                ["nullable"] = comp.NullableContextOptions.ToString(),
                ["allow_unsafe"] = comp.AllowUnsafe,
                ["warning_level"] = comp.WarningLevel,
                ["general_diagnostic_option"] = comp.GeneralDiagnosticOption.ToString(),
                ["specific_diagnostic_options"] = comp.SpecificDiagnosticOptions.OrderBy(kv => kv.Key).ToDictionary(kv => kv.Key, kv => kv.Value.ToString()),
                ["check_overflow"] = comp.CheckOverflow,
                ["optimization"] = comp.OptimizationLevel.ToString(),
            },
            ["metadata_references"] = project.MetadataReferences.OfType<PortableExecutableReference>().Select(r => r.FilePath ?? SaveInMemoryReference(r)).ToList(),
            ["has_analyzer_references"] = project.AnalyzerReferences.Any(),
        };
        if (includeReferences)
        {
            d["project_references"] = project.ProjectReferences
                .Select(r => project.Solution.GetProject(r.ProjectId))
                .Where(p => p is not null)
                .Select(p => DescribeProject(p!, includeReferences: false))
                .ToList();
        }

        return d;
    }

    // A test may reference an assembly it compiled in memory (MetadataReference.CreateFromImage). Save its
    // metadata block so the harness can rebuild the reference (ModuleMetadata.CreateFromMetadata).
    private static unsafe string SaveInMemoryReference(PortableExecutableReference r)
    {
        var md = (AssemblyMetadata)r.GetMetadata();
        var reader = md.GetModules()[0].GetMetadataReader();
        byte[] bytes = new ReadOnlySpan<byte>(reader.MetadataPointer, reader.MetadataLength).ToArray();
        string dir = Path.Combine(Environment.GetEnvironmentVariable("CORPUS_DUMP_DIR")!, "refs");
        Directory.CreateDirectory(dir);
        using var sha = SHA256.Create();
        string path = Path.Combine(dir, Convert.ToHexString(sha.ComputeHash(bytes)).Substring(0, 16).ToLowerInvariant() + ".mdblob");
        lock (Gate)
        {
            if (!File.Exists(path))
            {
                File.WriteAllBytes(path, bytes);
            }
        }

        return "mdblob:" + path;
    }

    private static string Hash(string s)
    {
        using var sha = SHA256.Create();
        return Convert.ToHexString(sha.ComputeHash(Encoding.UTF8.GetBytes(s))).Substring(0, 16).ToLowerInvariant();
    }
}
