def build_node_activation_prompt(question: str, evidence: str, schema: str) -> str:
    return f"""You are an expert proficient in SQL databases. You must extract the required table names and column names from the database schema based on the user's question and evidence, and additionally identify the equivalence relations.

##1. Characteristics of Equivalence Relations
(1) The fields exist physically in the database tables and can be directly found in the table creation statements; they are not derived from calculations such as Column A / Column B, Column A + Column B, or other arithmetic operations.
(2) The filter condition must be written in the format: table.column = fixed_value. That is to say, the field exists in this column. Operations such as division, multiplication, CAST conversion, or function calculations are not allowed.

##2. Reference Examples
Example 1
Question: "What is the free rate for students between the ages of 5 and 17 at the school run by Kacey Gibson?"
Evidence: "Eligible free rates for students aged 5-17 = Free Meal Count (Ages 5-17) / Enrollment (Ages 5-17)"
Involved table names: schools, frpm
Involved column names: schools.CDSCode, schools.AdmFName1, schools.AdmLName1, frpm.CDSCode, frpm.Free Meal Count (Ages 5-17), frpm.Enrollment (Ages 5-17)
Equivalence relations: schools.AdmFName1 = Kacey, schools.AdmLName1 = Gibson

Example 2
Question: "Please list the lowest three eligible free rates for students aged 5-17 in continuation schools."
Evidence: "Eligible free rates for students aged 5-17 = Free Meal Count (Ages 5-17) / Enrollment (Ages 5-17)"
Involved table names: frpm
Involved column names: frpm.Educational Option Type, frpm.Free Meal Count (Ages 5-17), frpm.Enrollment (Ages 5-17)
Equivalence relations: frpm.Educational Option Type = Continuation School

Example 3
Question: "For the first client who opened his/her account in Prague, what is his/her account ID?"
Evidence: "A3 stands for region names"
Involved table names: account, district
Involved column names: account.account_id, account.district_id, account.date, district.A3
Equivalence relations: district.A3 = Prague

Example 4
Question: "Please list the phone numbers of the direct charter-funded schools that are opened after 2000/1/1."
Evidence: "Charter schools refers to Charter School (Y/N) = 1 in the frpm"
Involved table names: frpm, schools
Involved column names: frpm.CDSCode, frpm.Charter Funding Type, frpm.Charter School (Y/N), schools.CDSCode, schools.Phone, schools.OpenDate
Equivalence relations: frpm.Charter Funding Type = Directly funded, frpm.Charter School (Y/N) = 1

##3. Counterexamples
Example 1
Question: "For the school with the highest average score in Reading in the SAT test, what is its FRPM count for students aged 5-17?"
Evidence: ""
Involved table names: satscores, frpm
Involved column names: satscores.cds, satscores.AvgScrRead, frpm.CDSCode, frpm.FRPM Count (Ages 5-17)
Equivalence relations: satscores.cds = frpm.CDSCode
Reason: A and B are both columns

Example 2
Question: "How many schools in merged Lake have number of test takers less than 100?"
Evidence: ""
Involved table names: schools, satscores
Involved column names: schools.CDSCode, schools.StatusType, schools.County, satscores.cds, satscores.NumTstTakr
Equivalence relations: schools.District = merged Lake
Reason: According to semantics, schools.StatusType = Merged and schools.County = Lake

##4. Task to Solve
（1）Question: {question}
（2）Evidence: {evidence}
（3）Schema: {schema}

##5. Output Rules (MUST Follow Strictly)
(1) Your output must be in the following format:
Involved table names: table1, table2
Involved column names: table1.column1, table2.column2
Equivalence relations: table.column = fixed_value

(2) Involved table names must be exactly consistent with the schema, including case sensitivity.
(3) Involved column names must be exactly consistent with the schema, including case sensitivity.
(4) The column of Equivalence relations must exist in the list of Involved column names.
(5) Do not add any explanations or additional notes.
(6) Allow the equivalence relationship to be empty.
"""


def build_question_split_prompt(question: str) -> str:
    return f"""你是一个问题拆解专家，你需要把问题拆解成一系列子问题，这些子问题必须是原问题的真子集。

##一.拆解规则
（1）拆解后的所有子集均为原问题的真子集，禁止任何一个子集是原问题本身或与原问题等价，所有子集整合后可 1:1 还原原问题完整语义，无冗余、无遗漏、无增删义。
（2）所有子集脱离原问题上下文后仍可被单独精准理解；必须将原问题中的代词（their/its/they/it 等）替换为明确的指代对象，禁止模糊指代。
（3）子集间一定不知道彼此存在，一定不能存在依赖的模糊指代。
（4）拆解的子集不能太长，也就是说字数不宜过多，不能比原问题还长。

##二.例子
示例1
原问题：Rank schools by their average score in Writing where the score is greater than 499, showing their charter numbers.
拆解后的真子集：
（1）Rank schools by their average score in Writing.
（2）showing school charter numbers.
（3）the average score in Writing is greater than 499.

示例2
原问题：What is the highest eligible free rate for K-12 students in the schools in Alameda County?
拆解后的真子集
（1）What is the highest eligible free rate
（2）the eligible free rate for K-12 students
（3）the schools in Alameda County

示例3
原问题
Consider the average difference between K-12 enrollment and 15-17 enrollment of schools that are locally funded, list the names and DOC type of schools which has a difference above this average.
拆解后的真子集：
（1）What is the average difference between K-12 enrollment and 15-17 enrollment of locally funded schools?
（2）Which locally funded schools have a difference between K-12 enrollment and 15-17 enrollment above the average difference?
（3）What are the names and DOC type of these locally funded schools?

##三.你需要拆解的问题是：
{question}

##四.输出规则
（1）输出格式为：
    （1）真子集1
    （2）真子集2
                 .....
    （n）真子集n
（2）你的输出一定不能包含任何解释说明
"""


def build_supp_extract_prompt(evidence: str, sub_questions: str, schema: str) -> str:
    if evidence and str(evidence).strip():
        question_set = f"（0）{evidence}\n\n{sub_questions}"
        evidence_rule = "其中（0）是evidence，但是你也必须列出涉及的表和列。"
    else:
        question_set = sub_questions
        evidence_rule = "如果evidence为空，可以省略，不输出，直接从（1）开始。"

    return f"""You are an expert proficient in SQL databases. You must extract the required table names and column names from the database schema based on the user's question and evidence.There are many user issues, and each one is an independent issue. You must generate the required table and column names for them all. But these issues share the same evidence

##1. Reference Examples

Example 1

Question: "What is the free rate for students between the ages of 5 and 17 at the school run by Kacey Gibson?"

Evidence: "Eligible free rates for students aged 5-17 = Free Meal Count (Ages 5-17) / Enrollment (Ages 5-17)"

Involved table names: schools, frpm

Involved column names: schools.CDSCode, schools.AdmFName1, schools.AdmLName1, frpm.CDSCode, frpm.Free Meal Count (Ages 5-17), frpm.Enrollment (Ages 5-17)

Example 2

Question: "Please list the lowest three eligible free rates for students aged 5-17 in continuation schools."

Evidence: "Eligible free rates for students aged 5-17 = `Free Meal Count (Ages 5-17)` / `Enrollment (Ages 5-17)`"

Involved table names: frpm

Involved column names: frpm.Educational Option Type, frpm.Free Meal Count (Ages 5-17), frpm.Enrollment (Ages 5-17)

Example 3

Question: "For the first client who opened his/her account in Prague, what is his/her account ID?"

Evidence: "A3 stands for region names"

Involved table names: account, district

Involved column names: account.account_id, account.district_id, account.date, district.A3

Example 4

Question: "Please list the phone numbers of the direct charter-funded schools that are opened after 2000/1/1."

Evidence: "Charter schools refers to Charter School (Y/N) = 1 in the frpm"

Involved table names: frpm, schools

Involved column names: frpm.CDSCode, frpm.Charter Funding Type, frpm.Charter School (Y/N), schools.CDSCode, schools.Phone, schools.OpenDate

##2. You need to solve the following problems (note that each problem needs to be solved)

(1) Question set：

{question_set}

(2) Shared evidence: {evidence}

(3) Schema: {schema}

3.处理规则

问题集合里有几个问题，你就要输出几个答案。比如问题输出里面有

（0）

（1）

（2）

（3）

四个问题，你就要为这四个问题都找到涉及的表和列。{evidence_rule}

##4. Output Rules (MUST Follow Strictly)

(1) Your output must be in the following format:

Involved table names: table1, table2

Involved column names: table1.column1, table2.column2

(2) Involved table names must be exactly consistent with the schema, including case sensitivity—double-check carefully.

(3) Involved column names must be exactly consistent with the schema, including case sensitivity.

(4) Do not add any explanations or additional notes to your output. Adhere strictly to the format specified in (1).

(5) If evidence is empty, it can be omitted and not output, starting directly from (1).
"""


def build_sql_generation_messages(
    question: str,
    evidence: str,
    relationship,
    new_schema: str,
    examples: str,
    column_value_hints: str = "",
    sql_dialect: str = "SQLite",
) -> list[dict[str, str]]:
    relationship_str = "\n".join(relationship) if isinstance(relationship, list) else str(relationship)

    return [
        {
            "role": "system",
            "content": f"""You are a senior {sql_dialect} Text-to-SQL expert.

Generate exactly one valid {sql_dialect} SQL query for the user's question.

Rules:
1. Output SQL only. Do not output explanations, comments, markdown, or code fences.
2. The SQL must start with SELECT and must be a single complete statement.
3. Use only tables and columns from the provided Database Schema.
4. Do not invent tables, columns, values, aliases, or filters.

## SELECT Output Rules
5. SELECT clause must contain only the final answer columns explicitly asked by the question.
6. Do not include intermediate/helper columns in SELECT, including:
   - columns used only for ORDER BY
   - columns used only for WHERE filters
   - columns used only for JOIN conditions
   - columns used only for GROUP BY
   - metric columns used only to rank rows
   - entity/name columns not explicitly requested
7. Preserve the exact output column order requested by the question.
8. If the question asks for one attribute, SELECT exactly one column or one expression.
9. If the question asks for multiple attributes, SELECT only those attributes and in the same order as the question.

## Evidence and Formula Rules
10. External knowledge defines formulas and domain meanings. Follow it exactly when it provides a calculation.
11. Do not replace an evidence formula with a precomputed rate/percentage column unless the evidence explicitly says so.
12. When dividing numeric columns, use CAST(numerator AS REAL) when needed to avoid integer division.

## Known Mapping Relationship Rules
13. Known mapping relationships are verified candidate value mappings. Use only the relationships necessary for answering the current question.
14. If a relationship is clearly relevant, use its exact table.column and value.
15. Do not replace a relevant relationship with a semantically similar column from schema comments.
16. Do not add irrelevant relationships as extra filters.

## Column Value Hint Rules
17. Column Value Hints provide real distinct database values from activated columns.
18. When using a value for a hinted column, use the value exactly as shown.
19. Do not rewrite, expand, translate, normalize, or change capitalization of hinted values.
20. If the question mentions a natural-language value and Column Value Hints show the corresponding database value, use the hinted database value.

## Table and JOIN Rules
21. If one table already contains all required output, filter, and calculation columns, prefer a single-table query.
22. Do not introduce JOINs unless columns from multiple tables are truly required.
23. When joining tables, use only valid key columns shown in the Database Schema.

## Reference Example Rules
24. Reference Examples may be grouped into A/B/C sections:
   - A Current Database Semantic Examples: same database, selected by natural-language similarity. You may learn table usage, column usage, join patterns, business formulas, and SQL style from them, but only when consistent with the provided Database Schema.
   - B Current Database SQL-Structure Examples: same database, selected by SQL structure similarity to a draft SQL. You may learn SQL structure and current-database query patterns from them.
   - C Global SQL-Structure Examples: may come from other databases or another SQL dialect. Use them only for SQL structure. Never copy their table names, column names, literal values, or business meanings.
25. The provided Database Schema and External knowledge always have higher priority than reference examples.

## Ranking and NULL Rules
26. For top-N / lowest-N / highest-N questions, use ORDER BY with LIMIT.
27. When the question asks for fields from the row with the highest/lowest metric, prefer ORDER BY metric DESC/ASC LIMIT n instead of WHERE metric = MAX/MIN(metric).
28. When ordering by a nullable metric, add IS NOT NULL if a valid non-null value is required.

## SQL Dialect Rules
29. Quote identifiers with backticks when needed, especially when names contain spaces, parentheses, hyphens, slashes, reserved words, or special characters.
30. The SQL must conform to {sql_dialect} syntax."""
        },
        {
            "role": "user",
            "content": f"""Question:
{question}

External knowledge:
{evidence}

Known mapping relationships:
{relationship_str}

Relationship note:
A relationship such as "schools.StatusType = Closed" means the value "Closed" exists in schools.StatusType.
Use only relationships that are necessary for this question.
If a relationship is relevant, use its exact table.column and value.
Do not replace it with a similar column from schema comments.

Column Value Hints:
{column_value_hints if column_value_hints else "No column value hints."}

Column value hint note:
question-matched values are matched from the current question/evidence and have higher priority than frequent values.
When using a value from Column Value Hints, copy it exactly.
Do not change capitalization.
Do not remove leading zeros.

Database Schema:
{new_schema}

Reference SQL Patterns:
{examples}

Generate the final {sql_dialect} SQL query only."""
        },
    ]
