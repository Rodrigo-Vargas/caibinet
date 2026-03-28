You are a file organization assistant. Analyze the content below and return **only** valid JSON — no explanation, no markdown.

Rules:
- Use lowercase_underscores for filename.
- Do not invent facts.
- Be consistent across similar files.
- Choose category from: Finance, Work, Personal, Media, Code, Other.

Output exactly:
{"filename": "...", "category": "Finance|Work|Personal|Media|Code|Other", "path": "relative/suggested/path/", "confidence": 0.0–1.0, "reasoning": "one sentence"}

File metadata: name=report_q1_2025.txt, extension=.txt, size=240 bytes

Content:
Q1 2025 Financial Report
========================

Revenue: $1,200,000
Expenses: $850,000
Net profit: $350,000

Key highlights:
- Product line A exceeded targets by 12%
- New partnership signed with Acme Corp
- Headcount grew from 45 to 52


Output:

{
  "filename": "report_q1_2025.txt",
  "category": "Finance",
  "path": "./report_q1_2025.txt",
  "confidence": 1.0,
  "reasoning": "This file contains the Q1 2025 financial report with revenue and expense details."
}