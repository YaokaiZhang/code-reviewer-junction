# Requirements

Numbered requirement lines per issue. Lines marked *(inferred)* are our reading, not the issue text.

## 2234 — The analyzer does not work if SuppressSourceGeneration = true

Source: the issue title only; we did not have the issue body.

- R-2234-1: The analyzer reports its diagnostics for `[MessagePackObject(SuppressSourceGeneration = true)]` types.
- R-2234-2 *(inferred)*: For any list of keyed members, collecting keys never throws, whatever keys repeat or mix kinds. (This is the theorem in the brief. It is false for the branch: see proof.json.)
- R-2234-3 *(inferred)*: Every member whose key repeats an earlier key, or has the other key kind, gets a diagnostic.
- R-2234-4 *(inferred)*: The fix does not remove diagnostics that base reported.

## 2297 — Add ExcludeFromCodeCoverage attribute to generated code

Source: the branch title and commit message only; we did not have the issue text.

- R-2297-1 *(inferred)*: Every type the source generator emits (formatters and resolvers) carries `[ExcludeFromCodeCoverage]`.
- R-2297-2 *(inferred)*: Generated code still compiles for every consumer target MessagePack supports (netstandard2.0, netstandard2.1, net472, net8.0), and it compiles for existing user code that already compiled.
- R-2297-3 *(inferred)*: Apart from the attribute, generated output does not change.
- R-2297-4 *(inferred)*: The README describes the behaviour accurately.
