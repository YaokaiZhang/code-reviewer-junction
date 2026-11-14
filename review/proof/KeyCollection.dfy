// Model of the key-collection logic in GetObjectInfo
// (src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs), base 32258fdb vs branch ju26-issue-2234.
//
// Input: the members that carry a [Key] attribute, in the order the C# visits them
// (all properties first, then all fields). Each key is an int, a string, or neither
// ([Key(null)]: the attribute is there but its value is neither int nor string).
// Output: the int-key map, the string-key map (key -> index of the member that holds it),
// and the reports (diagnostics) raised, or Fail when the C# would throw.
//
// Places where the C# throws, and how they are modelled:
//   intKey!.Value with intKey == null         -> Fail  (InvalidOperationException)
//   Dictionary.Add with a key already present -> Fail  (ArgumentException)       [base only]
//   Dictionary.ContainsKey(null)              -> Fail  (ArgumentNullException)
// The properties loop guards the string branch with `else if (stringKey is not null)`;
// the fields loop uses a bare `else`. That difference is modelled by Kind.
//
// No `assume`, no `{:axiom}`.

datatype Key = I(n: int) | S(s: string) | N
datatype Kind = Prop | Field
datatype Member = M(kind: Kind, key: Key)
datatype Report = BothNull(i: nat) | Mix(i: nat) | Dup(i: nat)
datatype State = St(searchFirst: bool, isInt: bool, ints: map<int, nat>, strs: map<string, nat>, reports: seq<Report>)
datatype Res = Ok(st: State) | Fail(at: nat)

const Init: State := St(true, false, map[], map[], [])

// ---------- branch ju26-issue-2234 ----------

function BodyNew(st: State, m: Member, i: nat): Res
{
  if st.isInt then
    if !m.key.I? then Fail(i)
    else
      var k := m.key.n;
      var r := if k in st.ints then st.reports + [Dup(i)] else st.reports;
      Ok(st.(ints := if k in st.ints then st.ints else st.ints[k := i], reports := r))
  else if m.kind == Prop && !m.key.S? then Ok(st)            // `else if (stringKey is not null)` not taken
  else if !m.key.S? then Fail(i)                             // fields loop: ContainsKey(null)
  else
    var k := m.key.s;
    var r := if k in st.strs then st.reports + [Dup(i)] else st.reports;
    Ok(st.(strs := if k in st.strs then st.strs else st.strs[k := i], reports := r))
}

function StepNew(st: State, m: Member, i: nat): Res
{
  var st1 := if m.key.N? then st.(reports := st.reports + [BothNull(i)]) else st;
  if st1.searchFirst then BodyNew(st1.(searchFirst := false, isInt := m.key.I?), m, i)
  else if (st1.isInt && !m.key.I?) || (!st1.isInt && !m.key.S?) then Ok(st1.(reports := st1.reports + [Mix(i)]))  // new `continue`
  else BodyNew(st1, m, i)
}

function CollectNew(ms: seq<Member>): Res
  decreases |ms|
{
  if |ms| == 0 then Ok(Init)
  else
    match CollectNew(ms[..|ms|-1])
    case Fail(j) => Fail(j)
    case Ok(st) => StepNew(st, ms[|ms|-1], |ms|-1)
}

// ---------- base 32258fdb ----------

function BodyOld(st: State, m: Member, i: nat): Res
{
  if st.isInt then
    if !m.key.I? then Fail(i)
    else
      var k := m.key.n;
      if k in st.ints then Fail(i)                           // reports Dup, then Dictionary.Add throws
      else Ok(st.(ints := st.ints[k := i]))
  else if m.kind == Prop && !m.key.S? then Ok(st)
  else if !m.key.S? then Fail(i)
  else
    var k := m.key.s;
    if k in st.strs then Fail(i)
    else Ok(st.(strs := st.strs[k := i]))
}

function StepOld(st: State, m: Member, i: nat): Res
{
  var st1 := if m.key.N? then st.(reports := st.reports + [BothNull(i)]) else st;
  if st1.searchFirst then BodyOld(st1.(searchFirst := false, isInt := m.key.I?), m, i)
  else if (st1.isInt && !m.key.I?) || (!st1.isInt && !m.key.S?) then BodyOld(st1.(reports := st1.reports + [Mix(i)]), m, i)  // no continue
  else BodyOld(st1, m, i)
}

function CollectOld(ms: seq<Member>): Res
  decreases |ms|
{
  if |ms| == 0 then Ok(Init)
  else
    match CollectOld(ms[..|ms|-1])
    case Fail(j) => Fail(j)
    case Ok(st) => StepOld(st, ms[|ms|-1], |ms|-1)
}

// ---------- theorems ----------

// The theorem as first stated ("collecting keys never fails, whatever keys repeat or mix kinds")
// is FALSE for the branch: a type whose first keyed member is a field with [Key(null)] fails.
lemma LockedTheoremIsFalseForBranch()
  ensures CollectNew([M(Field, N)]) == Fail(0)
{
}

// Exact characterisation: on the branch, collection fails if and only if the first keyed
// member is a field whose key is neither int nor string.
predicate Inv(ms: seq<Member>, st: State)
{
  |ms| > 0 && !st.searchFirst && st.isInt == ms[0].key.I?
}

lemma NewOkInv(ms: seq<Member>)
  requires |ms| > 0 && ms[0] != M(Field, N)
  ensures CollectNew(ms).Ok? && Inv(ms, CollectNew(ms).st)
  decreases |ms|
{
  if |ms| > 1 {
    var p := ms[..|ms|-1];
    assert p[0] == ms[0];
    NewOkInv(p);
  }
}

lemma BranchFailsIffFirstIsNullKeyField(ms: seq<Member>)
  ensures CollectNew(ms).Fail? <==> (|ms| > 0 && ms[0] == M(Field, N))
{
  if |ms| > 0 && ms[0] == M(Field, N) {
    FailSticks(ms);
  } else if |ms| > 0 {
    NewOkInv(ms);
  }
}

lemma FailSticks(ms: seq<Member>)
  requires |ms| > 0 && ms[0] == M(Field, N)
  ensures CollectNew(ms) == Fail(0)
  decreases |ms|
{
  if |ms| > 1 {
    var p := ms[..|ms|-1];
    assert p[0] == ms[0];
    FailSticks(p);
  }
}

// The weaker theorem that does hold: with no [Key(null)] field in first position — in particular
// for any mix and repetition of int and string keys — collection never fails.
lemma BranchNeverFailsForIntAndStringKeys(ms: seq<Member>)
  requires forall j :: 0 <= j < |ms| ==> !ms[j].key.N?
  ensures CollectNew(ms).Ok?
{
  BranchFailsIffFirstIsNullKeyField(ms);
}

// Base fails on a repeated key (the bug the branch fixes) and on a mixed key.
lemma BaseFailsOnDuplicateIntKey()
  ensures CollectOld([M(Prop, I(0)), M(Prop, I(0))]) == Fail(1)
{
}

lemma BaseFailsOnDuplicateStringKey()
  ensures CollectOld([M(Prop, S("a")), M(Prop, S("a"))]) == Fail(1)
{
}

lemma BaseFailsOnIntThenString()
  ensures CollectOld([M(Prop, I(0)), M(Prop, S("a"))]) == Fail(1)
{
}

// Finding (b): first wins, and every later member that repeats an accepted key gets a Dup report.
function KeyOf(m: Member): Key { m.key }

predicate SameKind(first: Member, m: Member)
{
  (first.key.I? && m.key.I?) || (!first.key.I? && m.key.S?)
}

lemma DupReported(ms: seq<Member>)
  requires |ms| > 0 && ms[0] != M(Field, N)
  ensures CollectNew(ms).Ok?
  ensures var st := CollectNew(ms).st;
    (forall k :: k in st.ints ==> (st.ints[k] < |ms| && ms[st.ints[k]].key == I(k)
                                   && (forall j :: 0 <= j < st.ints[k] ==> ms[j].key != I(k))))
    && (forall k :: k in st.strs ==> (st.strs[k] < |ms| && ms[st.strs[k]].key == S(k)
                                   && (forall j :: 0 <= j < st.strs[k] ==> ms[j].key != S(k))))
    && (forall i :: 0 <= i < |ms| && SameKind(ms[0], ms[i]) && (exists j :: 0 <= j < i && ms[j].key == ms[i].key)
          ==> Dup(i) in st.reports)
    && (forall i: nat :: Dup(i) in st.reports ==> 0 <= i < |ms| && exists j :: 0 <= j < i && ms[j].key == ms[i].key)
    && (forall i :: 0 <= i < |ms| && SameKind(ms[0], ms[i]) && ms[i].key.I? ==> ms[i].key.n in st.ints)
    && (forall i :: 0 <= i < |ms| && SameKind(ms[0], ms[i]) && ms[i].key.S? ==> ms[i].key.s in st.strs)
  decreases |ms|
{
  NewOkInv(ms);
  if |ms| > 1 {
    var p := ms[..|ms|-1];
    assert p[0] == ms[0];
    DupReported(p);
    NewOkInv(p);
    var stp := CollectNew(p).st;
    var i := |ms| - 1;
    assert forall j :: 0 <= j < |p| ==> p[j] == ms[j];
  }
}
