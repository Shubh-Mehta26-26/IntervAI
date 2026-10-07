"""Original small problem collection authored for IntervAI; not copied from a collection."""

from sqlalchemy import select

from app.models.coding import CodingProblem, CodingTestCase
from app.schemas.coding import ProblemInput

STARTERS = {
    "python": "import sys\n\ndef solve():\n    data = list(map(int, sys.stdin.read().split()))\n    # Implement your solution here.\n    pass\n\nsolve()\n",
    "cpp": "#include <iostream>\n#include <vector>\nusing namespace std;\nint main() {\n    // Read stdin and write your answer to stdout.\n    return 0;\n}\n",
    "java": "import java.util.*;\npublic class Main {\n    public static void main(String[] args) {\n        Scanner in = new Scanner(System.in);\n        // Implement your solution here.\n    }\n}\n",
}


def definitions():
    specs = [
        (
            "balance-total",
            "Ledger balance",
            "Arrays",
            1,
            "A ledger contains signed changes. Compute the final balance starting from zero. Return one signed integer.",
            "First an integer n, then n signed integers.",
            "The sum of the n changes.",
            [
                ("4\n8 -3 2 -7\n", "0"),
                ("1\n-5\n", "-5"),
                ("0\n", "0"),
                ("5\n100 -1 -1 -1 -1\n", "96"),
            ],
            "d=list(map(int,input().split())); n=d[0]; import sys; a=d[1:]+list(map(int,sys.stdin.read().split())); print(sum(a[:n]))",
            "int n; cin>>n; long long sum=0,x; while(n--){cin>>x;sum+=x;} cout<<sum;",
            "int n=in.nextInt(); long sum=0; for(int i=0;i<n;i++)sum+=in.nextLong(); System.out.println(sum);",
        ),
        (
            "repeat-labels",
            "Repeated sensor labels",
            "Hash tables",
            2,
            "A stream contains integer sensor labels. Count distinct labels that appear at least twice. Each repeated label counts once regardless of frequency.",
            "First n, followed by n integer labels.",
            "The number of distinct repeated labels.",
            [
                ("6\n3 3 7 8 7 3\n", "2"),
                ("3\n1 2 3\n", "0"),
                ("0\n", "0"),
                ("5\n-1 -1 -1 -1 -1\n", "1"),
            ],
            "import sys; from collections import Counter; a=list(map(int,sys.stdin.read().split())); print(sum(v>=2 for v in Counter(a[1:1+a[0]]).values()))",
            "int n,x;cin>>n; map<int,int> c;while(n--){cin>>x;c[x]++;} int ans=0;for(auto p:c)ans+=p.second>=2;cout<<ans;",
            "int n=in.nextInt(); Map<Integer,Integer> c=new HashMap<>(); for(int i=0;i<n;i++){int x=in.nextInt();c.put(x,c.getOrDefault(x,0)+1);} int ans=0;for(int v:c.values())if(v>=2)ans++;System.out.println(ans);",
        ),
        (
            "first-threshold",
            "First reading at threshold",
            "Binary search",
            3,
            "Read a sorted nondecreasing list of sensor readings and a threshold. Find the zero-based index of the first reading at least the threshold. Print -1 if none exists. Use binary search.",
            "First n and threshold t, then n sorted signed integers.",
            "First index with value >= t, or -1.",
            [
                ("5 4\n1 4 4 9 12\n", "1"),
                ("3 10\n1 2 3\n", "-1"),
                ("0 2\n", "-1"),
                ("4 -3\n-3 -3 0 8\n", "0"),
            ],
            "import sys,bisect; d=list(map(int,sys.stdin.read().split())); n,t=d[:2]; a=d[2:]; i=bisect.bisect_left(a,t); print(i if i<n else -1)",
            "int n,t;cin>>n>>t;vector<int>a(n);for(int&x:a)cin>>x;int l=0,r=n;while(l<r){int m=l+(r-l)/2;if(a[m]<t)l=m+1;else r=m;}cout<<(l<n?l:-1);",
            "int n=in.nextInt(),t=in.nextInt();int[]a=new int[n];for(int i=0;i<n;i++)a[i]=in.nextInt();int l=0,r=n;while(l<r){int m=l+(r-l)/2;if(a[m]<t)l=m+1;else r=m;}System.out.println(l<n?l:-1);",
        ),
    ]
    specs.extend(
        [
            (
                "peak-balance",
                "Peak ledger balance",
                "Arrays",
                2,
                "A ledger starts at zero and receives signed changes in order. Return the highest balance ever reached, including the initial zero balance. Do not reorder the changes.",
                "First n, followed by n signed changes.",
                "The maximum prefix balance, at least zero.",
                [
                    ("4\n5 -2 4 -9\n", "7"),
                    ("3\n-1 -2 -3\n", "0"),
                    ("0\n", "0"),
                    ("5\n2 -2 3 -3 8\n", "8"),
                ],
                "import sys,itertools; d=list(map(int,sys.stdin.read().split())); print(max([0]+list(itertools.accumulate(d[1:1+d[0]]))))",
                "int n;cin>>n;long long s=0,b=0,x;while(n--){cin>>x;s+=x;if(s>b)b=s;}cout<<b;",
                "int n=in.nextInt();long s=0,b=0;for(int i=0;i<n;i++){s+=in.nextLong();b=Math.max(b,s);}System.out.println(b);",
            ),
            (
                "label-frequency",
                "Most frequent label count",
                "Hash tables",
                3,
                "A stream contains integer labels. Return the largest occurrence count of any single label, or zero for an empty stream. Label identity and order do not affect the returned count.",
                "First n, followed by n integer labels.",
                "Maximum frequency, or zero for no labels.",
                [
                    ("6\n3 3 7 8 7 3\n", "3"),
                    ("3\n1 2 3\n", "1"),
                    ("0\n", "0"),
                    ("5\n-1 -1 -1 -1 -1\n", "5"),
                ],
                "import sys;from collections import Counter;d=list(map(int,sys.stdin.read().split()));print(max(Counter(d[1:1+d[0]]).values(),default=0))",
                "int n,x,b=0;cin>>n;map<int,int>c;while(n--){cin>>x;int v=++c[x];if(v>b)b=v;}cout<<b;",
                "int n=in.nextInt(),b=0;Map<Integer,Integer>c=new HashMap<>();for(int i=0;i<n;i++){int x=in.nextInt(),v=c.getOrDefault(x,0)+1;c.put(x,v);b=Math.max(b,v);}System.out.println(b);",
            ),
            (
                "threshold-count",
                "Readings within threshold",
                "Binary search",
                4,
                "Given sorted nondecreasing sensor readings and a threshold, count readings less than or equal to the threshold. Use a binary-search boundary rather than scanning the list after input is read.",
                "First n and threshold t, followed by n sorted integers.",
                "Number of readings <= t.",
                [
                    ("5 4\n1 4 4 9 12\n", "3"),
                    ("3 0\n1 2 3\n", "0"),
                    ("0 5\n", "0"),
                    ("4 8\n-3 -3 0 8\n", "4"),
                ],
                "import sys,bisect;d=list(map(int,sys.stdin.read().split()));print(bisect.bisect_right(d[2:],d[1]))",
                "int n,t;cin>>n>>t;vector<int>a(n);for(int&x:a)cin>>x;int l=0,r=n;while(l<r){int m=l+(r-l)/2;if(a[m]<=t)l=m+1;else r=m;}cout<<l;",
                "int n=in.nextInt(),t=in.nextInt();int[]a=new int[n];for(int i=0;i<n;i++)a[i]=in.nextInt();int l=0,r=n;while(l<r){int m=l+(r-l)/2;if(a[m]<=t)l=m+1;else r=m;}System.out.println(l);",
            ),
        ]
    )
    for (
        slug,
        title,
        topic,
        difficulty,
        description,
        input_format,
        output_format,
        cases,
        py,
        cpp,
        java,
    ) in specs:
        tests = [{"input": x, "expected": y} for x, y in cases]
        yield (
            slug,
            ProblemInput(
                title=title,
                description=description,
                difficulty=difficulty,
                topic=topic,
                skills=[topic],
                constraints=["0 <= n <= 10000", "Every integer has absolute value <= 1000000"],
                input_format=input_format,
                output_format=output_format,
                examples=tests[:2],
                starter_code=STARTERS,
                supported_languages=list(STARTERS),
                public_tests=tests[:2],
                hidden_tests=tests[2:],
                reference_solutions={
                    "python": py,
                    "cpp": "#include <iostream>\n#include <vector>\n#include <map>\nusing namespace std; int main(){"
                    + cpp
                    + "}",
                    "java": "import java.util.*; public class Main {public static void main(String[]args){Scanner in=new Scanner(System.in);"
                    + java
                    + "}}",
                },
            ),
        )


async def insert_problem(db, payload, owner=None, slug=None, provenance=None):
    values = payload.model_dump(exclude={"public_tests", "hidden_tests"})
    row = CodingProblem(
        **values,
        candidate_id=owner,
        slug=slug,
        provenance=provenance or {"source": "candidate-authored"},
    )
    db.add(row)
    await db.flush()
    for ordinal, (hidden, case) in enumerate(
        [(False, c) for c in payload.public_tests] + [(True, c) for c in payload.hidden_tests], 1
    ):
        db.add(
            CodingTestCase(problem_id=row.id, ordinal=ordinal, hidden=hidden, **case.model_dump())
        )
    await db.flush()
    return row


async def ensure_catalog(db):
    # Serialize first-use catalog creation without another queue or uniqueness race.
    from sqlalchemy import text

    await db.execute(text("SELECT pg_advisory_xact_lock(923019)"))
    for slug, payload in definitions():
        if not await db.scalar(select(CodingProblem.id).where(CodingProblem.slug == slug)):
            await insert_problem(
                db,
                payload,
                slug=slug,
                provenance={
                    "source": "IntervAI original",
                    "version": "1",
                    "validation": "pending real reference execution",
                },
            )
