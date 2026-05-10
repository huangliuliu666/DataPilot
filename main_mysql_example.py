from agent.text2sql_agent import Text2SQLAgent


def main() -> None:
    agent = Text2SQLAgent()
    agent.connect_mysql(
        db_id="local_mysql_demo",
        host="127.0.0.1",
        port=3306,
        user="root",
        password="你的MySQL密码",
        database="你的数据库名",
        auto_train_schema=True,
    )

    agent.train_documentation(
        db_id="local_mysql_demo",
        documentation="在这里补充业务指标定义，例如 GMV = order_amount。",
    )

    answer = agent.ask(
        db_id="local_mysql_demo",
        question="这里输入你的自然语言问题",
        run_sql=True,
    )

    print(answer["sql"])
    print(answer.get("result"))


if __name__ == "__main__":
    main()
