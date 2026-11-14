import json, collections
R="https://github.com/MessagePack-CSharp/MessagePack-CSharp"
def P(n): return f"{R}/pull/{n}"
def S(who,quote,n,anchor=None,date=None,base=None):
    u=(base or P(n))+(("#"+anchor) if anchor else "")
    d={"who":who,"quote":quote,"url":u}
    if date: d["date"]=date
    return d
prs=[]
def add(**k):
    k.setdefault("merge_commit",None); k.setdefault("original_commit",None); k.setdefault("files_hint",None)
    k["url"]=P(k["pr"]); prs.append(k)

I2040=f"{R}/issues/2040"
# ---------------- reverts
add(pr=2013,title="Secure by default",date="2024-10-18",outcome="reverted",concern="compat-breaking",
 statements=[S("AArnott","Use the UntrustedData security policy by default.",2013,"issue-2595260076","2024-10-17"),
  S("AArnott","This is by design because v3 now runs in UntrustedData mode by default.",None,None,"2024-10-24",I2040),
  S("neuecc","This is too big of a breaking change.",None,None,"2024-10-28",I2040),
  S("AArnott","Revert to v2's insecure-by-default mode (effectively reverts Secure by default #2013)",2045,None,"2024-10-29")],
 merge_commit="c1585ad7",original_commit="c1585ad7",revert_commit="16bda3d9 (merged via PR #2045, 1eb17e5b)",
 files_hint="src/MessagePack, tests/MessagePack.Tests, doc/migrating_v2-v3.md, README.md",
 notes="Reverted 11 days after merge when issue #2040 showed custom-key dictionaries broke under UntrustedData; #2045 kept a 500 stack-depth limit even for trusted data.")
add(pr=1678,title="Allow applying `[MessagePackFormatter]` on parameters",date="2023-09-19",outcome="reverted",concern="other",
 statements=[S("AArnott","This shouldn't have merged into `master`. It should have been targeting `develop`. See #1680",1679,None,"2023-09-19")],
 merge_commit="fe50eef3",original_commit="fe50eef3",revert_commit="cf0b7d74 (merged via PR #1679, ec99ca7a)",
 files_hint="src/MessagePack.UnityClient (shared sources)",
 notes="Branch-targeting revert, not a code objection; re-landed against develop as #1680 (5356dfb6).")
add(pr=1124,title="Target .NET Core 3.1 and 5.0 SDKs in mpc tool (re-land of reverted 'Multiple Target Frameworks')",date="2020-11-19",outcome="reverted",concern="targets",
 statements=[S("AArnott","We need it to work in both worlds or we alienate a bunch of users.",1124,"pullrequestreview-534474658","2020-11-19")],
 merge_commit="e03abbb6",original_commit="cd7b4341",revert_commit="cc07ead1 (inside PR #1123, merge e3db213d)",
 files_hint="src/MessagePack.Generator, src/MessagePack.GeneratorCore, global.json",
 notes="cd7b4341 'Multiple Target Frameworks' was pushed into the unrelated PR #1123 and reverted by its author, then submitted on its own as #1124. AArnott's change request was withdrawn the same day after he found a dotnet restore mistake in his repro; the quote still states the requirement that mpc work on both SDKs.")
add(pr=777,title="Improve performance of standard decimal serialization by using Utf8Formatter",date="2020-01-17",outcome="reverted",concern="performance",
 statements=[S("neuecc","use Utf8Formatter instead of ToString to avoid string allocation.",777,"issue-550299951","2020-01-15"),
  S("AArnott","Very nice optimization!",777,"pullrequestreview-343363141","2020-01-15")],
 merge_commit="dfd964c5",original_commit="31bd18c1",revert_commit="4b8e2a37",
 files_hint="src/MessagePack.UnityClient/.../Formatters/StandardClassLibraryFormatter.cs",
 notes="31bd18c1 was pushed directly to master by neuecc and reverted by him the same day (4b8e2a37), then reviewed as PR #777. No written reason for the revert; the PR got further review fixes (decimal fallback/length checks) before merge. Not used as a rule source.")
# ---------------- closed unmerged
add(pr=1895,title="Performance/1807 force method inline",date="2024-12-10",outcome="closed-unmerged",concern="generated",
 statements=[S("AArnott","You'd have to change the `.tt` file instead and let that update the `.cs` files.",1895,"discussion_r1687026969","2024-07-22"),
  S("AArnott","you can see how adding the attribute doesn't change the compiled assembly at all",1895,"discussion_r1687035484","2024-07-22"),
  S("neuecc","The structure has changed significantly in v3, so it is necessary to start over.",1895,"issuecomment-2531213700","2024-12-10")],
 files_hint="src/MessagePack (T4 .tt templates and generated .cs)")
add(pr=1733,title=".NET 8 Update(7): Throw Exception Helper functions",date="2024-01-15",outcome="closed-unmerged",concern="readability",
 statements=[S("AArnott","I don't want a bunch of `#if` statements for something so trivially addressible in another way.",1733,"discussion_r1449803697","2024-01-12"),
  S("AArnott","Just create an `internal static` helper class that has the if and throw check inside it,",1733,"discussion_r1449803697","2024-01-12")],
 notes="Closed by the author pending the #1734 restructure, after the change request.")
add(pr=1828,title="Move BuildTypeName() from TypelessFormatter to MessagePackSerializerOptions",date="2024-05-27",outcome="closed-unmerged",concern="public-api",
 statements=[S("AArnott","is a defective design as it leads to unexpected, unpredictable results.",1828,"issuecomment-2132512201","2024-05-27"),
  S("AArnott","I suggest opening an issue to discuss before making the code changes to avoid any lost effort.",1828,"issuecomment-2132512201","2024-05-27"),
  S("AArnott","Also, I try to avoid formatter-specific members on the options class because the latter is more general.",1828,"issuecomment-2133497527","2024-05-27")])
add(pr=1755,title="Add TargetFramework netstandard2.1 for Unity",date="2024-01-30",outcome="closed-unmerged",concern="targets",
 statements=[S("AArnott","The takeaway is that no, we should _not_ assume that `#if NETSTANDARD2_1` code will only run on unity.",1755,"issuecomment-1917662763","2024-01-30"),
  S("pCYSl5EDgo","Then I guess we should not increase the number of TargetFrameworks that we support.",1755,"issuecomment-1917711947","2024-01-30")])
add(pr=1697,title="Handle DataContract(Order=N) across class hierarchies?",date="2023-11-10",outcome="closed-unmerged",concern="wire-format",
 statements=[S("AArnott","I suspect you break backward compatibility with this change.",1697,"issuecomment-1797111678","2023-11-07"),
  S("AArnott","But with your change, things _appear_ to just work until the data isn't compatible across versions any more.",1697,"issuecomment-1797111678","2023-11-07")])
add(pr=1690,title="Add Unity.Mathematics support",date="2024-12-10",outcome="closed-unmerged",concern="maintainability",
 statements=[S("neuecc","This PR would cause problems in an environment where Unity.Mathematics is not installed.",1690,"issuecomment-1764453369","2023-10-16"),
  S("neuecc","Therefore, could you please separate the assemblies?",1690,"issuecomment-1785060792","2023-10-30"),
  S("neuecc","Let's stop putting it in the StandardResolver.",1690,"issuecomment-2255204882","2024-07-29"),
  S("neuecc","Preventing this from occurring is more important and non-negotiable than Mathematics support.",1690,"issuecomment-2333118505","2024-09-06")],
 files_hint="src/MessagePack.UnityClient")
add(pr=1312,title="Add Unity mathematics support",date="2022-02-13",outcome="closed-unmerged",concern="maintainability",
 statements=[S("neuecc","How about separating it into a separate asmdef?",1312,"issuecomment-902539892","2021-08-20"),
  S("AArnott","It's still failing... Can you fix?",1312,"issuecomment-959804733","2021-11-03")],
 notes="Closed by stale bot after CI kept failing.")
add(pr=1694,title="Support to analyze records and record structs",date="2023-10-29",outcome="closed-unmerged",concern="tests",
 statements=[S("AArnott","Can you add a test for the shorter record syntax?",1694,"pullrequestreview-1702219344","2023-10-27"),
  S("AArnott","going forward we want to work on `develop` without a bunch of merge conflicts with main.",1694,"pullrequestreview-1702219344","2023-10-27")],
 notes="Author re-submitted against develop as #1698 (merged f7808587).")
add(pr=1854,title="Support generics in analyzer",date="2024-07-19",outcome="closed-unmerged",concern="scope",
 statements=[S("AArnott","We won't take the PR if it only works for master and creates merge conflicts in develop.",1854,"issuecomment-2186498734","2024-06-24"),
  S("AArnott","But `develop` is very much the priority right now.",1854,"issuecomment-2186498734","2024-06-24")])
add(pr=1957,title="Fix source generated resolver containing invalid code when array of array type is used",date="2024-09-25",outcome="closed-unmerged",concern="scope",
 statements=[S("AArnott","Mine is much more expansive, changing the object model we use to represent data types more exhaustively",1957,"issuecomment-2374029946","2024-09-25")],
 notes="Superseded by a maintainer PR fixing the same bug more broadly.")
add(pr=1636,title="Changed version of System.Collections.Immutable to 6.0.0",date="2023-06-12",outcome="closed-unmerged",concern="maintainability",
 statements=[S("AArnott","Thank you, but we need a bigger and more maintainable fix than this.",1636,"issuecomment-1586427588","2023-06-12")],
 notes="Superseded by #1641 (1cefde9b).")
add(pr=1621,title="Remove Analyzers.Only PackageId",date="2023-05-20",outcome="closed-unmerged",concern="other",
 statements=[S("AArnott","This fix was incomplete, because it was not sufficient to suppress the bad package ref.",1621,"issuecomment-1555916472","2023-05-20")],
 notes="Closed in favor of #1622 (522b7e50).")
add(pr=1626,title="Add support for Fluent protocol DateTime ext format",date="2023-06-12",outcome="closed-unmerged",concern="scope",
 statements=[S("AArnott","Closing due to no response on the linked issue.",1626,"issuecomment-1586395127","2023-06-12")])
add(pr=1609,title="Expose written bytes from MessagePackWriter.",date="2023-05-20",outcome="closed-unmerged",concern="scope",
 statements=[S("AArnott","Closing due to no response on the underlying issue.",1609,"issuecomment-1555927976","2023-05-20")])
add(pr=1542,title="MessagePack.Generator.csproj target to net7.0",date="2023-03-11",outcome="closed-unmerged",concern="targets",
 statements=[S("AArnott","The master branch still uses the .NET 6 SDK so you can't target .NET 7.",1542,"issuecomment-1341805530","2022-12-08")],
 notes="No explicit closing reason; closed alongside #1564.")
add(pr=1441,title="Get private setter and getter from base classes via reflection in DynamicObjectResolver",date="2022-12-10",outcome="closed-unmerged",concern="scope",
 statements=[S("AArnott","I don't think we want `Static` properties. A serializer has no business handling static data.",1441,"discussion_r891709396","2022-06-07"),
  S("AArnott","Why are you setting `Key(0)` here on a type where the property name is meant to be the key?",1441,"discussion_r891710348","2022-06-07")],
 files_hint="src/MessagePack (DynamicObjectResolver.cs)",notes="Went stale after the change request; closed by AArnott after a stale-bot notice.")
add(pr=1416,title="Fix for \"System.NotImplementedException: byref delegate\"",date="2022-06-07",outcome="closed-unmerged",concern="scope",
 statements=[S("AArnott","The answer for iOS is to use AOT, per our README file.",1416,"pullrequestreview-998572043","2022-06-07"),
  S("AArnott","Let's have a discussion around whether that works for you before we make more code changes to the library.",1416,"pullrequestreview-998572043","2022-06-07"),
  S("AArnott","This couldn't compile, as you're declaring the `serialize` local twice.",1416,"discussion_r891519259","2022-06-07")])
add(pr=1374,title="MPC: Reduce Memory Allocation",date="2022-05-20",outcome="closed-unmerged",concern="maintainability",
 statements=[S("neuecc","I'm against it because it adds too many unnecessary dependencies.",1374,"issuecomment-1004119890","2022-01-03"),
  S("neuecc","It is terrible to embed so many logics in a template.",1374,"issuecomment-1004707810","2022-01-04"),
  S("neuecc","It is hard to read and hard to debug.",1374,"issuecomment-1004707810","2022-01-04"),
  S("neuecc","It is more important to keep the code base clean.",1374,"issuecomment-1005567533","2022-01-05")],
 files_hint="src/MessagePack.GeneratorCore (T4 templates)",notes="Closed by stale bot.")
add(pr=1369,title="Code generator supports init only setter",date="2022-04-06",outcome="closed-unmerged",concern="compat-breaking",
 statements=[S("AArnott","Now the property setter is invoked with `default(T)` when no data is in the stream.",1369,"issuecomment-1002726721","2021-12-29"),
  S("AArnott","That would overwrite any other value set by the class constructor or a property initializer, which would break reasonably expected prior behavior.",1369,"issuecomment-1002726721","2021-12-29"),
  S("pCYSl5EDgo","You should execute bat files before git commit in order to pass the CI.",1369,"issuecomment-1002870275","2021-12-30")],
 files_hint="src/MessagePack.GeneratorCore",notes="Closed by stale bot.")
add(pr=1074,title="Beautify T4 of mpc.exe and reduce local variables of the deserialization",date="2020-10-17",outcome="closed-unmerged",concern="compat-breaking",
 statements=[S("AArnott","Rejecting this till the breaking change is justified",1074,"pullrequestreview-511006338","2020-10-17"),
  S("AArnott","We should only take breaking changes if their value significantly outweighs the risk of breaking folks,",1074,"issuecomment-711061875","2020-10-17"),
  S("AArnott","We want to keep the AOT and dynamic resolver behavior equivalent.",1074,"issuecomment-711061875","2020-10-17")],
 files_hint="src/MessagePack.GeneratorCore (T4)",notes="Cherry-picked as f86ec028 (#1088) in a reduced form.")
add(pr=998,title="Add support for sortKeys on the MessagePackObjectAttribute",date="2020-08-08",outcome="closed-unmerged",concern="scope",
 statements=[S("neuecc","sortKeys is not needed at all.",998,"issuecomment-670276954","2020-08-07"),
  S("neuecc","Usually, the order of the map is not guaranteed.",998,"issuecomment-670276954","2020-08-07"),
  S("AArnott","you could also use the official library and use your own formatter that writes out properties in the order you require.",998,"issuecomment-671143154","2020-08-10")])
add(pr=950,title="Added Support for Programmatically inserting Unions",date="2020-08-03",outcome="closed-unmerged",concern="maintainability",
 statements=[S("neuecc","It doesn't look like a good design to handle it in the same resolver.",950,"issuecomment-643146205","2020-06-12"),
  S("neuecc","It would be better if they were independent, like the CompositeResolver.",950,"issuecomment-643146205","2020-06-12")])
add(pr=889,title="Enable support for platforms (e.g. Blazor WASM) where System.Reflection.Emit is not supported.",date="2020-04-19",outcome="closed-unmerged",concern="public-api",
 statements=[S("AArnott","Changing from a field to a property is a binary breaking change. We can't do that within a major version.",889,"discussion_r410767424","2020-04-18")],
 notes="Closed by the author.")
add(pr=847,title="Bring back MessagePackBinary class for write methods",date="2020-05-08",outcome="closed-unmerged",concern="performance",
 statements=[S("AArnott","I don't think we should take it because it does complicate the code",847,"pullrequestreview-383328814","2020-03-28"),
  S("AArnott","So I'm pretty pessimistic on this idea based on maintenance cost.",847,"issuecomment-623462509","2020-05-04"),
  S("AArnott","it certainly doesn't warrant sacrificing perf on all our existing scenarios.",847,"issuecomment-625620132","2020-05-08"),
  S("AArnott","If you do find a way to resolve the perf regressions as found by our benchmarks, feel free to comment here",847,"issuecomment-625620132","2020-05-08")])
add(pr=645,title="Bring back binary compatability with version 1.8.74",date="2019-11-19",outcome="closed-unmerged",concern="compat-breaking",
 statements=[S("AArnott","The breaking changes are why we gave it a 2.0 version",645,"issuecomment-555589493","2019-11-19"),
  S("AArnott","I don't want to start going down the path of appeasing some 1.x folks since there's no end to that path.",645,"issuecomment-555589493","2019-11-19")])
# ---------------- merged after changes / merged
add(pr=1884,title="Avoid regenerating all formatters when only one object/union/enum changes",date="2024-07-19",outcome="merged-after-changes",concern="other",
 statements=[S("AArnott","This is insufficient, for the same reason we need to implement our own `Equals` method",1884,"discussion_r1680105459","2024-07-16"),
  S("AArnott","An invariant that we must hold is that GetHashCode return the same value from two objects",1884,"discussion_r1680105459","2024-07-16"),
  S("AArnott","Why is this necessary?",1884,"discussion_r1680103811","2024-07-16")],
 merge_commit="ae2a1ca1",files_hint="src/MessagePack.SourceGenerator, tests/MessagePack.SourceGenerator.Tests")
add(pr=1634,title="Union type collect",date="2023-08-13",outcome="merged-after-changes",concern="tests",
 statements=[S("AArnott","Thank you for this. Might I prevail upon you to add a test for this case?",1634,"pullrequestreview-1495650941","2023-06-23")],
 merge_commit="f54d0cd3",files_hint="src/MessagePack.Analyzers, sandbox/TestData2")
add(pr=1551,title="Fix wrong data length written in `UnsafeBlitFormatter`",date="2023-03-12",outcome="merged-after-changes",concern="public-api",
 statements=[S("AArnott","Thanks for the fix. It merits some discussion before merging.",1551,"pullrequestreview-1263978742","2023-01-20"),
  S("AArnott (commit eb8c898)","Also move the API from Shipped to Unshipped, because it has not in fact shipped yet.",1551,None,"2023-03-12")],
 merge_commit="58c4d3cc",files_hint="src/MessagePack, src/MessagePack.UnityClient, tests/MessagePack.Tests")
add(pr=1137,title="Avoid `MissingMethodException` on generic classes with `init` property setters",date="2021-01-29",outcome="merged-after-changes",concern="compat-breaking",
 statements=[S("neuecc","Also, the behavior of quietly returning a null is hard to notice and makes it easy for users to bury serious bugs.",1137,"pullrequestreview-537353863","2020-11-24"),
  S("neuecc","But we had to be aware that there was a breaking changes.",1137,"issuecomment-734151655","2020-11-26"),
  S("AArnott","I think it's a good change in behavior given the reasons I include in that doc.",1137,"issuecomment-749156997","2020-12-21")],
 merge_commit="2ec0f139",files_hint="src/MessagePack.UnityClient, tests/MessagePack.Tests, README.md")
add(pr=1285,title="Add string interning option",date="2021-09-02",outcome="merged-after-changes",concern="performance",
 statements=[S("AArnott","It looks to me like this may be inescapable perf cost if you want interning.",1285,"issuecomment-886130679","2021-07-25"),
  S("AArnott","So the question is, should we have it off by default?",1285,"issuecomment-886130679","2021-07-25"),
  S("neuecc","It would be preferable if it were not included in the options, but it is going to be difficult to use.",1285,"pullrequestreview-704888910","2021-07-13")],
 merge_commit="683d464b",files_hint="src/MessagePack, src/MessagePack.UnityClient, README.md",
 notes="Interning ended up opt-in (commit 6e4fd8d 'Remove string interning by default') via StringInterningFormatter.")
add(pr=1743,title="AOT by default",date="2024-01-30",outcome="merged-after-changes",concern="compat-breaking",
 statements=[S("neuecc","StandardAotResolver is introduced in 2.6-alpha track so not shiped yet.",1743,"issuecomment-1913286310","2024-01-27"),
  S("neuecc","Therefore, I don't think it will be a breaking change. What do you think?",1743,"issuecomment-1913286310","2024-01-27"),
  S("AArnott","Changes applied.",1743,"issuecomment-1913325485","2024-01-27")],
 merge_commit="9c804613",files_hint="src/MessagePack, src/MessagePack.SourceGenerator, tests/MessagePack.SourceGenerator.Tests")
add(pr=2139,title="Change ByteListFormatter behaviour to keep binary compatibility for List<byte>",date="2025-01-27",outcome="merged",concern="wire-format",
 statements=[S("neuecc","The correct behavior should be returning identical serialization results across all platforms.",2139,"issue-2808388873","2025-01-24"),
  S("neuecc","This is a breaking change that requires careful consideration.",2139,"issue-2808388873","2025-01-24"),
  S("neuecc","we decided to support both array and binary deserialization.",2139,"issue-2808388873","2025-01-24")],
 merge_commit=None,notes="Merged to master as e823ea1, which exists in the local clone but is not an ancestor of base 32258fdb (develop line). Approved by AArnott without comment.")
add(pr=1355,title=".NET 6 Update",date="2021-12-25",outcome="merged-after-changes",concern="targets",
 statements=[S("neuecc","I think we should add net6.0 to mpc targetframeworks.",1355,"issuecomment-986546329","2021-12-06")],
 merge_commit="fed033dd",files_hint="src/MessagePack, src/MessagePack.GeneratorCore, tools/Install-DotNetSdk.ps1")

# ---------------- rules
rules_src=[
("compat-breaking","Do not take breaking changes (behavioral or binary) unless their value clearly outweighs the risk to existing users; justify any you propose.",[(1074,"pullrequestreview-511006338"),(1074,"issuecomment-711061875"),(2013,None),(645,"issuecomment-555589493"),(1137,"issuecomment-734151655")]),
("public-api","Public API shape is frozen within a major version: e.g. changing a public field to a property is binary breaking and not allowed.",[(889,"discussion_r410767424"),(645,"issuecomment-555589493")]),
("wire-format","Serialized output must stay compatible across versions and identical across platforms/targets; a change that silently alters the bytes produced for existing types is rejected or needs a read-both-forms migration.",[(1697,"issuecomment-1797111678"),(2139,"issue-2808388873")]),
("compat-breaking","Deserialization must not overwrite values the type itself set (constructor or initializer) when a member is missing from the data, and should fail loudly rather than quietly return null.",[(1369,"issuecomment-1002726721"),(1137,"pullrequestreview-537353863")]),
("compat-breaking","Keep the AOT (source-generated) and dynamic resolver behavior equivalent; a change to one must be matched in the other.",[(1074,"issuecomment-711061875")]),
("generated","Never hand-edit generated .cs files; change the .tt template (or generator) and regenerate.",[(1895,"discussion_r1687026969"),(1369,"issuecomment-1002870275")]),
("maintainability","Keep logic out of T4 templates and do not add unnecessary dependencies to the generator; a clean code base outranks micro-savings in tooling.",[(1374,"issuecomment-1004707810"),(1374,"issuecomment-1005567533"),(1374,"issuecomment-1004119890")]),
("performance","Performance claims need evidence: an optimization attribute or refactor that does not change compiled output or regresses benchmarks is not accepted.",[(1895,"discussion_r1687035484"),(847,"issuecomment-625620132")]),
("performance","Features with a significant performance cost must be opt-in, not on by default.",[(1285,"issuecomment-886130679")]),
("maintainability","Optional or platform-specific integrations (e.g. Unity.Mathematics) go in a separate assembly/asmdef and their own resolver, never into StandardResolver or the core assembly.",[(1690,"issuecomment-1785060792"),(1690,"issuecomment-2255204882"),(1312,"issuecomment-902539892"),(950,"issuecomment-643146205")]),
("readability","Prefer a small internal static helper over sprinkling #if blocks through code for trivial checks such as throw helpers.",[(1733,"discussion_r1449803697")]),
("public-api","Avoid formatter-specific members on MessagePackSerializerOptions and virtual hooks whose effect depends on which options instance is seen first.",[(1828,"issuecomment-2133497527"),(1828,"issuecomment-2132512201")]),
("targets","Do not add target frameworks lightly, and do not assume a TFM (e.g. netstandard2.1) implies a particular runtime such as Unity; tools must keep working on the SDKs users already have.",[(1755,"issuecomment-1917662763"),(1755,"issuecomment-1917711947"),(1124,"pullrequestreview-534474658")]),
("other","Target feature work at the active branch (develop at the time) rather than master; changes that merge only to master and conflict with develop are reverted or declined.",[(1679,None),(1854,"issuecomment-2186498734"),(1694,"pullrequestreview-1702219344")]),
("tests","Bug fixes and new analyzer/generator cases need a test covering the case.",[(1634,"pullrequestreview-1495650941"),(1694,"pullrequestreview-1702219344")]),
("scope","Discuss larger or design-level changes in an issue first; PRs whose linked issue goes unanswered, or that are superseded by a broader maintainer fix, get closed.",[(1828,"issuecomment-2132512201"),(1416,"pullrequestreview-998572043"),(1626,"issuecomment-1586395127"),(1609,"issuecomment-1555927976"),(1957,"issuecomment-2374029946")]),
("scope","The serializer handles instance data only; out-of-scope features (static members, guaranteed map key ordering) are declined in favor of custom formatters.",[(1441,"discussion_r891709396"),(998,"issuecomment-670276954"),(998,"issuecomment-671143154")]),
("other","Value types used for change detection must implement GetHashCode consistently with their custom Equals (including array fields).",[(1884,"discussion_r1680105459")]),
("public-api","APIs that have not shipped yet belong in PublicAPI.Unshipped.txt; changing unshipped API is not a breaking change.",[(1551,None),(1743,"issuecomment-1913286310")]),
("maintainability","Prefer complete, maintainable fixes over minimal patches (e.g. a version bump or a partial package-ref suppression).",[(1636,"issuecomment-1586427588"),(1621,"issuecomment-1555916472")]),
]
rules=[]
for i,(c,txt,srcs) in enumerate(rules_src,1):
    urls=[]
    for n,a in srcs:
        urls.append(P(n)+("#"+a if a else "") if n!=2013 else I2040)
    # verify each source url appears as a statement url, or PR url
    allurls={s["url"] for p in prs for s in p["statements"]}
    for u in urls: assert u in allurls, u
    rules.append({"id":f"H-{i:02d}","concern":c,"rule":txt,"sources":urls,"times_cited":len({u.split('#')[0] for u in urls})})
for p in prs:
    for s in p["statements"]: assert len(s["quote"])<=300
oc=collections.Counter(p["outcome"] for p in prs); cc=collections.Counter(p["concern"] for p in prs)
doc={"check":"project-history","repo":"MessagePack-CSharp/MessagePack-CSharp","cutoff":"2025-03-01","produced_by":"hand",
"method":"Revert commits were found with `git log 32258fdb -i --grep=^revert` in the local clone and traced to their original commits/PRs via merge-commit messages; closed-unmerged PRs came from the github.com closed+unmerged PR list (pages 1-4 and a non-dependabot page) and merged PRs from searches for review:changes_requested and \"breaking change\" commented by AArnott. Each PR page was read with WebFetch; quotes are verbatim excerpts (the fetch tool limits quote length, so some are sentence fragments) and every rule cites at least one quoted statement dated on or before 2025-03-01.",
"summary":f"{len(prs)} PRs ("+", ".join(f"{v} {k}" for k,v in oc.most_common())+f"); {len(rules)} rules; 5 infrastructure reverts from Library.Template not pursued.",
"prs":prs,"rules":rules,
"reverts_not_pursued":[
 {"commit":"75d85ec0","subject":"Revert \"Bump dotnet-coverage to 17.8.7\"","why":"Library.Template build-infrastructure merge (#230 from AArnott/sdkUpdate8), not project code review"},
 {"commit":"ac247b85","subject":"Revert \"Add completions for dotnet-test-cloud script\"","why":"Library.Template infra; commit says it disallowed non-default config names"},
 {"commit":"d3cb4c58","subject":"Revert \"Include README in nupkg\"","why":"Library.Template infra; due to NuGet/Home#10791"},
 {"commit":"69a74f8c","subject":"Revert incremental install of SDKs/Runtimes","why":"Library.Template infra (buggy SDK install optimization)"},
 {"commit":"cae9277e","subject":"Revert \"Use PowerShell Core in Azure Pipelines\"","why":"Library.Template infra"},
 {"commit":"25ba6449, e1f7a71a, f86ec028, cf5038e4","subject":"match ^revert only incidentally","why":"not reverts of a PR (wording inside larger commits)"}],
"skipped_no_maintainer_reason":[2054,1887,1750,1744,1606,1488,895],
"fetch_failures":[
 {"what":"api.github.com and mcp github tools","why":"blocked by proxy / repo not configured for session; github.com HTML via curl returned 403, so all pages were read with WebFetch"},
 {"what":"Comment anchors for issue #2040","why":"WebFetch summary did not expose comment ids; statements link the issue page"},
 {"what":"Inline review text for PR #777 (pullrequestreview-343373132) and second half of long pages (#1551, #1634, #1884, #1743, #2139)","why":"not visible in fetched portion; not re-fetched to stay within budget"}]}
out="/home/user/code-reviewer-junction/review/context/history.json"
json.dump(doc,open(out,"w"),indent=2,ensure_ascii=False)
print(doc["summary"]); print(dict(cc))
for r in rules: print(r["id"],r["concern"],r["times_cited"],r["rule"])
