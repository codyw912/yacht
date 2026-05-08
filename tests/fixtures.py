REGATTA_CONFIG = """
[regatta]
name = "memory-smoke-test"

[course]
name = "tiny-course"
tasks = [
  { id = "task-1", title = "Fix a failing test", difficulty = 1 },
  { id = "task-2", title = "Add a CLI flag", difficulty = 2 },
]

[[vessels]]
name = "baseline"
model = "mock-fast"

[[vessels]]
name = "memory-rig"
model = "mock-fast"
rigging = ["memory"]
"""


INVALID_REGATTA_CONFIG = """
[regatta]
name = "broken-regatta"

[course]
name = "tiny-course"
tasks = []

[[vessels]]
name = "baseline"
model = "mock-fast"
"""
