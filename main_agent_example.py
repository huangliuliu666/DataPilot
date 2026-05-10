import os

from agent.text2sql_agent import Text2SQLAgent


def main() -> None:
    db_path = os.getenv("TEXT2SQL_EXAMPLE_SQLITE_PATH")
    if not db_path:
        raise RuntimeError(
            "Set TEXT2SQL_EXAMPLE_SQLITE_PATH to a local SQLite database path before running this example."
        )

    agent = Text2SQLAgent()

                                                                                    
                                                                  
    agent.connect_sqlite(
        db_id=os.getenv("TEXT2SQL_EXAMPLE_DB_ID", "california_schools"),
        db_path=db_path,
    )

    db_id = os.getenv("TEXT2SQL_EXAMPLE_DB_ID", "california_schools")

    agent.train_documentation(
        db_id=db_id,
        documentation=(
            "Eligible free rate for K-12 = `Free Meal Count (K-12)` / `Enrollment (K-12)`. "
            "When calculating rate/ratio/percentage metrics in SQLite, cast the numerator as REAL. "
            "For highest rate questions, prefer ORDER BY ratio_expression DESC LIMIT 1."
        ),
    )

    answer = agent.ask(
        db_id=db_id,
        question="What is the highest eligible free rate for K-12 students in Alameda County?",
        run_sql=True,
    )

    print(answer["sql"])
    print(answer["result"])


if __name__ == "__main__":
    main()
