"""Authored starter lessons. Study choices never create assessed skill or gap evidence."""

import re
from copy import deepcopy
from datetime import datetime, timezone


def lesson(title, explanation, example, exercise, question, options, answer, feedback):
    return {
        "title": title,
        "explanation": explanation,
        "examples": [example],
        "practice_question": exercise,
        "hints": ["Explain your assumptions, work through the example, then test an edge case."],
        "quiz": {"question": question, "options": options, "answer": answer, "feedback": feedback},
    }


TRACKS = {
    "javascript": {
        "title": "JavaScript", "category": "Frontend", "aliases": ["JavaScript", "Node.js"],
        "description": "Understand data flow, closures, and asynchronous work.",
        "lessons": [
            lesson(
                "Scope, closures, and predictable state",
                "A closure is a function that retains access to the lexical scope where it was created. Each call to an outer function can create a separate environment. const prevents rebinding; it does not freeze objects. Prefer small functions with explicit inputs, and distinguish local state from shared mutable state when explaining a bug.",
                "function counter() {\n  let count = 0;\n  return () => ++count;\n}\nconst next = counter();\nnext(); // 1\nnext(); // 2\ncounter()(); // 1: a separate closure",
                "Explain why next() remembers count. How would two independent counters behave? Show how shared state could accidentally couple them.",
                "What does the second call to next() return in the example?",
                ["1, because local state resets", "2, because the closure keeps its environment", "An error, because count is private"],
                1, "The returned function closes over count. Reusing that function reuses the same environment.",
            ),
            lesson(
                "Promises, await, and failure handling",
                "An async function returns a Promise. await pauses that function while other work can proceed; it does not block the whole browser. Independent requests can run together with Promise.all. A failed fetch HTTP status is not automatically a rejected promise, so check response.ok. Handle rejection and cleanup explicitly, and avoid starting duplicate requests on repeated clicks.",
                "async function loadUser(id) {\n  const response = await fetch(`/users/${id}`);\n  if (!response.ok) throw new Error('Request failed');\n  return response.json();\n}\ntry { await loadUser(7); } catch (error) { /* show a retry */ }",
                "Design a loading flow for two independent requests. Explain when Promise.all is appropriate and how you would handle one request failing.",
                "When does fetch normally reject?",
                ["For every HTTP 404 response", "Only when JSON parsing fails", "For a network failure; HTTP errors need status checks"],
                2, "fetch resolves for HTTP error responses. Check the status, and separately handle network and decoding errors.",
            ),
        ],
    },
    "react": {
        "title": "React", "category": "Frontend", "aliases": ["React", "React.js", "ReactJS", "Next.js"],
        "description": "Build reliable state, effects, and accessible forms.",
        "lessons": [
            lesson(
                "Render state and immutable updates",
                "React renders a snapshot of props and state. A setter schedules another render; it does not rewrite values inside an already running event handler. Use a functional update when the new value depends on the previous value. Copy arrays and objects instead of mutating state. Keep derived values calculated from existing state so that separate copies do not drift apart.",
                "const [items, setItems] = useState([]);\nfunction add(item) {\n  setItems(previous => [...previous, item]);\n}\nconst completed = items.filter(item => item.done).length;",
                "Explain why pushing into a state array can cause problems. Design state for a task list with a derived completion count.",
                "Which update safely depends on the current count?",
                ["setCount(previous => previous + 1)", "count++", "setCount = count + 1"],
                0, "The updater receives the latest pending state and returns the next value without mutating it.",
            ),
            lesson(
                "Effects, cleanup, and request races",
                "Use effects to synchronize with external systems, rather than to calculate values that rendering can derive. Include reactive dependencies. Clean up timers, subscriptions, and requests when dependencies change or a component unmounts. A slow old request can overwrite a newer result unless you cancel or ignore it. Always make loading, empty, success, and error states visible.",
                "useEffect(() => {\n  const controller = new AbortController();\n  fetch(url, { signal: controller.signal })\n    .then(r => r.json()).then(setData)\n    .catch(error => { if (error.name !== 'AbortError') setError(error.message); });\n  return () => controller.abort();\n}, [url]);",
                "A search for A finishes after a search for B. Explain the race and show how to prevent A from replacing B's results.",
                "When should an effect clean up its subscription?",
                ["Only when the browser closes", "Before rerunning with changed dependencies and on unmount", "On every keystroke regardless of dependencies"],
                1, "Cleanup undoes the previous synchronization before a replacement starts, and when the component leaves the page.",
            ),
        ],
    },
    "html-css": {
        "title": "HTML & CSS", "category": "Frontend", "aliases": ["HTML", "CSS", "Frontend Developer"],
        "description": "Create accessible, responsive interfaces with clear structure.",
        "lessons": [
            lesson(
                "Semantic HTML and keyboard access",
                "Choose elements by meaning: a button performs an action and a link navigates. Associate every form input with a visible label. Native buttons support keyboard activation and focus behavior. Use headings to organize content, give errors useful text, and preserve visible focus. A clickable div does not gain button behavior merely by looking like one.",
                '<form>\n  <label for="email">Email address</label>\n  <input id="email" type="email" required>\n  <button type="submit">Save</button>\n</form>',
                "Describe how you would make a login form usable with only a keyboard and explain how to announce validation errors.",
                "Which element should save a form?",
                ["A div with a click handler", "An anchor without an href", "A submit button"],
                2, "A submit button provides the correct semantics and built-in form and keyboard behavior.",
            ),
            lesson(
                "Responsive layouts without fixed assumptions",
                "Grid handles rows and columns; flexbox works well for arranging items along one main axis. Let content determine sizes where possible. minmax(0, 1fr) allows grid columns to shrink without long content forcing overflow. Use media queries when the layout needs a structural change. Test narrow viewports, long text, and keyboard focus rather than judging a single screenshot.",
                ".cards {\n  display: grid;\n  grid-template-columns: repeat(2, minmax(0, 1fr));\n  gap: 1rem;\n}\n@media (max-width: 600px) {\n  .cards { grid-template-columns: 1fr; }\n}",
                "Design a two-column dashboard that becomes one column on phones. How will long labels and large text affect it?",
                "Why use minmax(0, 1fr) for a flexible grid column?",
                ["To allow it to shrink below its content's intrinsic minimum", "To make all content zero pixels wide", "To turn grid into flexbox"],
                0, "The zero minimum prevents long unbroken content from forcing the track beyond its allocated width.",
            ),
        ],
    },
    "typescript": {
        "title": "TypeScript", "category": "Frontend", "aliases": ["TypeScript"],
        "description": "Model data safely and narrow uncertain inputs.",
        "lessons": [
            lesson(
                "Unions and narrowing",
                "A union models values with several possible shapes. A shared literal field can identify each variant and help TypeScript narrow it. Prefer explicit loading, success, and error variants over combinations of unrelated booleans. unknown requires validation before use; any disables useful checking. Narrow values with runtime checks instead of asserting that an uncertain shape must be correct.",
                "type Result =\n  | { status: 'success'; value: string }\n  | { status: 'error'; message: string };\nfunction describe(result: Result) {\n  return result.status === 'success' ? result.value : result.message;\n}",
                "Model an API request with loading, success, and error states. Explain how discriminated unions prevent impossible combinations.",
                "What does unknown require before reading a property?",
                ["Nothing; it acts exactly like any", "A suitable type or runtime check", "Disabling strict mode"],
                1, "unknown preserves safety by requiring narrowing before operations that assume a specific shape.",
            ),
            lesson(
                "Types and runtime validation",
                "TypeScript checks source code, but its types are erased at runtime. A type assertion cannot validate a server response. Validate untrusted JSON at the boundary, then convert it into a trusted application type. Optional properties and null represent different cases; handle them deliberately rather than hiding missing values with non-null assertions.",
                "function isUser(value: unknown): value is { name: string } {\n  return typeof value === 'object' && value !== null\n    && 'name' in value && typeof value.name === 'string';\n}",
                "An API returns a malformed user object despite a declared User type. Explain why and show where validation belongs.",
                "Does 'response as User' validate incoming JSON?",
                ["Yes, by checking each property", "Yes, but only in production", "No, assertions do not add runtime checks"],
                2, "A type assertion changes what the compiler assumes; it does not inspect actual data.",
            ),
        ],
    },
    "python": {
        "title": "Python", "category": "Backend", "aliases": ["Python", "FastAPI", "Django"],
        "description": "Reason about objects, iteration, and maintainable functions.",
        "lessons": [
            lesson(
                "Mutability and function defaults",
                "Names refer to objects. Lists and dictionaries are mutable; strings and tuples are immutable, though a tuple can contain mutable objects. Assignment does not copy an object. Default argument expressions are evaluated when the function is defined, so a list default can accidentally share state between calls. Use None and create a fresh list inside the function.",
                "def append_item(item, items=None):\n    if items is None:\n        items = []\n    items.append(item)\n    return items\n\nappend_item('a')  # ['a']\nappend_item('b')  # ['b']",
                "Explain the bug in def add(x, items=[]). Show how shallow copying differs from deep copying for nested lists.",
                "When is a Python function's default list created?",
                ["Once when the function is defined", "Before every call", "Only after the first exception"],
                0, "A mutable default is shared by calls that omit the argument. Creating a new object inside avoids this coupling.",
            ),
            lesson(
                "Generators and memory use",
                "A generator yields values on demand and suspends its execution between yields. It can process a large stream without first building a complete result list. Iteration consumes the generator, so traversing it again requires a new generator. Lazy processing reduces intermediate storage, but it does not make expensive operations free or eliminate the cost of retaining results elsewhere.",
                "def squares(values):\n    for value in values:\n        yield value * value\n\nresult = squares(range(3))\nlist(result)  # [0, 1, 4]\nlist(result)  # []: already consumed",
                "Design a generator that reads records and yields valid ones. Discuss memory usage, error handling, and whether the result can be traversed twice.",
                "What does the second list(result) produce here?",
                ["The original list again", "An empty list", "An automatically refreshed generator"],
                1, "A generator is an iterator whose values are consumed. Create a fresh generator for another traversal.",
            ),
        ],
    },
    "sql": {
        "title": "SQL & databases", "category": "Backend", "aliases": ["SQL", "PostgreSQL", "MySQL", "SQLite", "DBMS"],
        "description": "Write correct joins and explain transactions and indexes.",
        "lessons": [
            lesson(
                "Joins, grouping, and missing rows",
                "An inner join includes matching rows; a left join also retains unmatched rows from the left side. A condition on the right table in WHERE can discard those unmatched rows. COUNT(*) counts joined rows, while COUNT(right.id) skips nulls. Check one-to-many relationships before aggregating, because joining multiple child tables can multiply counts.",
                "SELECT u.id, COUNT(o.id) AS orders\nFROM users u\nLEFT JOIN orders o ON o.user_id = u.id\nGROUP BY u.id;\n-- Users with no orders remain, with a count of 0.",
                "Write a query showing every customer and their paid order count, including customers with none. Explain where the paid filter belongs.",
                "Which aggregate counts only matched non-null order IDs?",
                ["COUNT(*)", "COUNT(1)", "COUNT(o.id)"],
                2, "COUNT(expression) ignores nulls. A left join's unmatched row has a null right-side ID.",
            ),
            lesson(
                "Transactions and index trade-offs",
                "A transaction groups related changes so they commit or roll back together. Isolation controls how concurrent transactions interact; it is separate from atomicity. Indexes speed selected reads but cost storage and extra writes. Inspect a query plan rather than assuming an index is always used. Design constraints and transaction boundaries around invariants such as keeping a transfer balanced.",
                "BEGIN;\nUPDATE accounts SET balance = balance - 100 WHERE id = 1;\nUPDATE accounts SET balance = balance + 100 WHERE id = 2;\nCOMMIT;\n-- Real code must validate funds and coordinate concurrent updates.",
                "Explain how to transfer funds safely under concurrent requests. Discuss transactions, locking or isolation, constraints, and failure recovery.",
                "What trade-off does adding an index usually introduce?",
                ["Faster suitable reads, with extra storage and write work", "Faster every query without any cost", "Automatic prevention of all concurrency anomalies"],
                0, "Indexes can improve selected access paths, but maintaining them adds cost to inserts, updates, and deletes.",
            ),
        ],
    },
    "apis": {
        "title": "REST APIs", "category": "Backend", "aliases": ["REST APIs", "REST API", "RESTful APIs", "FastAPI", "Express"],
        "description": "Design dependable endpoints, validation, and retries.",
        "lessons": [
            lesson(
                "Resources, HTTP, and validation",
                "Represent resources with stable URLs and use HTTP methods consistently. GET reads data; POST commonly creates a resource; PATCH changes selected fields. Validate shape and bounds before business logic, authenticate the caller, and authorize access to each requested record. Return useful status codes and safe errors without exposing stack traces or credentials.",
                "GET /api/orders/42       -> 200 with an authorized order\nPOST /api/orders         -> 201 with the new order\nPATCH /api/orders/42     -> 200 with the changed order\nGET /api/orders/unknown  -> 404",
                "Design endpoints for a private task list. Explain validation, ownership checks, pagination, and how an unauthorized request is handled.",
                "Where should ownership of an order be checked?",
                ["Only in the frontend", "On the server for the requested record", "Only when the account is created"],
                1, "A client can change resource IDs. Every protected server operation must enforce ownership or explicit permission.",
            ),
            lesson(
                "Idempotency and safe retries",
                "A request may complete on the server even if its response never reaches the client. Retrying a creation request can duplicate work. An idempotency key lets the server recognize the same logical operation, validate that the payload matches, and return the saved result. Store the decision durably and use database constraints or locks to handle concurrent requests.",
                "POST /payments\nIdempotency-Key: operation-123\n{ amount: 100 }\n\nRetry the same operation with the same key.\nA different payload using that key should be rejected.",
                "A client times out after creating an order. Explain how to retry safely and how simultaneous requests with one key should behave.",
                "Which key should a retry of the same operation use?",
                ["A new key for every network attempt", "No key after a timeout", "The original logical operation's key"],
                2, "Reusing the operation key allows the server to replay its saved outcome and prevent duplicate side effects.",
            ),
        ],
    },
    "algorithms": {
        "title": "Data structures & algorithms", "category": "Fundamentals", "aliases": ["DSA", "Data structures", "Algorithms", "Problem solving", "Binary search"],
        "description": "Choose structures, explain complexity, and test edge cases.",
        "lessons": [
            lesson(
                "Hash maps and complexity",
                "Choose a data structure for the operations you need. A hash map usually offers average constant-time lookup, while a list search is linear. Hashing, collisions, resizing, and key equality affect actual behavior. Distinguish average and worst-case bounds. State both time and space cost; avoiding repeated scans often uses additional memory.",
                "def has_duplicate(values):\n    seen = set()\n    for value in values:\n        if value in seen:\n            return True\n        seen.add(value)\n    return False\n# Average O(n) time, O(n) extra space for hashable values.",
                "Find two numbers that sum to a target. Explain a hash-map solution, duplicate values, and how it compares with sorting first.",
                "What is the extra space bound of the shown duplicate check?",
                ["O(n), because seen may retain all inputs", "O(1), because there is one set variable", "O(log n), because sets are always trees"],
                0, "Space complexity measures stored data, rather than the number of variable names.",
            ),
            lesson(
                "Binary search and invariants",
                "Binary search requires a sorted search space or another monotonic condition. Maintain an invariant describing where a solution may remain. Use one interval convention consistently, such as a half-open interval [lo, hi). Each step must shrink the interval. Test empty input, one element, duplicates, and targets beyond both ends. Standard lookup takes logarithmic comparisons with random-access input.",
                "def lower_bound(a, target):\n    lo, hi = 0, len(a)\n    while lo < hi:\n        mid = (lo + hi) // 2\n        if a[mid] < target:\n            lo = mid + 1\n        else:\n            hi = mid\n    return lo",
                "Explain why lower_bound terminates and returns the first possible insertion position. Trace it on an empty list and duplicate values.",
                "Which property makes binary search valid?",
                ["The list must contain unique numbers", "The search condition must be monotonic", "The target must already exist"],
                1, "A monotonic condition lets a comparison eliminate one side while preserving every possible answer.",
            ),
        ],
    },
    "git": {
        "title": "Git & collaboration", "category": "Tools", "aliases": ["Git", "GitHub", "Version control"],
        "description": "Understand commits, branches, and conflict resolution.",
        "lessons": [
            lesson(
                "Working tree, staging, and commits",
                "The working tree contains current files. The index, or staging area, describes the next commit. A commit records a snapshot with a parent history. Review staged changes before committing and keep unrelated changes separate. Ignore generated files and local secrets; an ignore rule does not erase secrets already committed. A branch is a movable reference to a commit.",
                "git status\ngit diff\ngit add src/feature.py\ngit diff --staged\ngit commit -m 'Add validated input handling'",
                "Explain the difference between modified, staged, and committed files. Describe a review process that avoids including local secrets.",
                "What does git diff --staged show?",
                ["All files on the remote server", "Only ignored files", "The changes staged for the next commit"],
                2, "It compares the staging area with the current commit, letting you review the next snapshot.",
            ),
            lesson(
                "Merging and resolving conflicts",
                "A merge combines histories and may require you to resolve overlapping edits. Inspect both versions and understand the intended behavior before removing conflict markers. Stage the resolved files and complete the merge, then validate the result. Rebasing rewrites commit ancestry; coordinate before rewriting shared history. Avoid force pushes as a routine conflict solution.",
                "git fetch origin\ngit merge origin/main\n# Resolve conflicting files using both changes' intent.\ngit add src/feature.py\ngit commit",
                "Two people change validation in one function. Explain how you would resolve the conflict and verify that both requirements still hold.",
                "What should guide a conflict resolution?",
                ["The intended behavior of both changes", "Always keeping only your own lines", "Deleting the file to remove the conflict"],
                0, "Conflict markers identify overlapping text. A correct resolution must also preserve the required behavior.",
            ),
        ],
    },
    "docker": {
        "title": "Docker", "category": "Tools", "aliases": ["Docker", "Containers"],
        "description": "Run services with clear networking and persistent storage.",
        "lessons": [
            lesson(
                "Images, containers, and persistent data",
                "An image is a packaged filesystem and configuration. A container is a running instance with its own writable layer. Removing a container can discard data in that layer. Use a named volume or deliberate bind mount for persistent data, and keep credentials out of images. Rebuilding an image does not automatically migrate a database or restore a missing volume.",
                "services:\n  db:\n    image: postgres:17\n    volumes:\n      - database_data:/var/lib/postgresql/data\nvolumes:\n  database_data:",
                "Describe what happens to database data when a container is recreated with and without a persistent volume.",
                "Where should a local containerized database persist its data?",
                ["Only in a container's temporary writable layer", "In a deliberately managed volume or mount", "In a committed image layer after each request"],
                1, "A persistent volume survives ordinary container replacement. Its lifecycle and backups must still be managed.",
            ),
            lesson(
                "Service networking and readiness",
                "localhost refers to the environment making the connection. Within a container it usually refers to that container, rather than your host or another service. Compose services can reach each other by service name on a shared network. Host clients use published ports. A running process is not necessarily ready: use meaningful health checks and handle temporary dependency failures.",
                "# Inside the backend container:\nDATABASE_HOST=db\nDATABASE_PORT=5432\n# From a host application with a port mapping:\nDATABASE_HOST=127.0.0.1\nDATABASE_PORT=5434",
                "A backend container cannot reach a database at localhost. Explain the likely cause and how to check service names, ports, and readiness.",
                "What does localhost normally refer to inside a container?",
                ["Every service in the Compose project", "The host operating system by default", "That container's own network environment"],
                2, "Use the appropriate service hostname for container-to-container traffic and published ports for host clients.",
            ),
        ],
    },
    "java": {
        "title": "Java & OOP", "category": "Backend", "aliases": ["Java", "Object oriented programming", "OOP"],
        "description": "Explain encapsulation, interfaces, and value equality.",
        "lessons": [
            lesson(
                "Interfaces and encapsulation",
                "Encapsulation protects an object's invariants behind a deliberate API. An interface describes behavior without forcing one implementation. Depend on a small interface when callers should not care whether data comes from a database, memory, or an external service. Prefer composition when a type should use another behavior without promising an inheritance relationship it cannot satisfy.",
                "interface UserRepository {\n    User findById(long id);\n}\nclass UserService {\n    private final UserRepository users;\n    UserService(UserRepository users) { this.users = users; }\n}",
                "Design a notification service supporting email and SMS. Explain the interfaces, invariant checks, and how you would test it.",
                "What is a useful reason to depend on an interface?",
                ["To allow different implementations behind a stable contract", "To eliminate every runtime error", "To make all state public"],
                0, "A contract separates a caller's needs from implementation details and makes controlled substitution possible.",
            ),
            lesson(
                "Equality and hash-based collections",
                "For object references, == checks identity. equals can define logical equality. When equal objects are used in hash-based collections, they must have equal hashCode values. Avoid changing fields that define equality while an object is being used as a map key. Distinguish two references to one object from separate objects representing the same value.",
                'String a = new String("ready");\nString b = new String("ready");\na == b;      // false: different objects\na.equals(b); // true: equal text',
                "Explain the equals/hashCode contract and what could go wrong if a mutable field used by a map key changes after insertion.",
                "For objects that are equal according to equals, what must be true?",
                ["They must have the same reference", "Their hashCode values must be equal", "They must be created on the same line"],
                1, "Equal objects require equal hash codes. Different objects may share a hash code, so collisions still need equality checks.",
            ),
        ],
    },
    "interview-skills": {
        "title": "Interview communication", "category": "Communication", "aliases": ["Communication", "Teamwork", "Leadership", "Behavioral"],
        "description": "Give specific, structured answers and explain your reasoning.",
        "lessons": [
            lesson(
                "Build a specific STAR answer",
                "For a behavioral question, explain the Situation, Task, Action, and Result. Keep the context short and spend most of the answer on what you personally did and why. Use an honest outcome, including limitations or lessons learned. If you do not have a workplace example, clearly identify a relevant academic or personal project rather than inventing experience.",
                "Situation: Our project missed a milestone.\nTask: I owned the API integration.\nAction: I isolated failing cases, agreed on a smaller contract, and added a daily integration check.\nResult: We delivered the reduced scope and documented the remaining work.",
                "Describe a time you handled a disagreement or setback. Identify your own actions, the outcome, and what you would change.",
                "Which part should usually contain the most detail?",
                ["A long description of the company", "A list of unrelated technologies", "Your actions, reasoning, and observable result"],
                2, "Specific actions and outcomes help an interviewer understand your contribution instead of inferring it from general statements.",
            ),
            lesson(
                "Think aloud with a clear structure",
                "Start by restating the problem and clarifying important constraints. Explain a simple correct approach before optimizing. State assumptions, describe trade-offs, and test a concrete example. If you get stuck, say what you know and identify the uncertainty. A concise explanation with checked reasoning is more useful than rapidly naming many concepts.",
                "1. Clarify input size and duplicate handling.\n2. Explain a baseline approach.\n3. Identify the bottleneck.\n4. Propose an improvement and its costs.\n5. Trace a normal case and an edge case.",
                "Explain how you would approach an unfamiliar technical problem. Demonstrate a clarification, baseline, trade-off, and edge-case check.",
                "What is a useful first response to an ambiguous problem?",
                ["Clarify constraints and restate the goal", "Immediately name the most complex algorithm", "Assume every missing detail without mentioning it"],
                0, "Clarifying assumptions prevents solving a different problem and makes subsequent reasoning easier to follow.",
            ),
        ],
    },
}


def matching_tracks(text):
    return [
        key for key, track in TRACKS.items()
        if any(re.search(r"(?<![\w+#])" + re.escape(alias) + r"(?![\w+#])", text, re.I)
               for alias in track["aliases"])
    ]


def catalog_values():
    return [
        {"id": key, **{field: track[field] for field in ("title", "category", "description")},
         "lesson_count": len(track["lessons"]), "effort_minutes": len(track["lessons"]) * 15}
        for key, track in TRACKS.items()
    ]


def lesson_content(value):
    return {
        **deepcopy(value), "source_chunk_ids": [], "sources": [],
        "grounding_status": "authored", "generator": "starter-lessons-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
