import re
from typing import Any

from openai import OpenAI

from config import Config
from services.prompts import (
    build_node_activation_prompt,
    build_question_split_prompt,
    build_sql_generation_messages,
    build_supp_extract_prompt,
)


class ModelScopeWorkflowEngine:
    def __init__(self) -> None:
        if not Config.MODELSCOPE_API_KEY:
            raise RuntimeError("MODELSCOPE_API_KEY is not set. 请先在环境变量中配置 ModelScope API Key。")

        self.client = OpenAI(
            base_url=Config.MODELSCOPE_BASE_URL,
            api_key=Config.MODELSCOPE_API_KEY,
        )

    def _clean_output(self, text: str) -> str:
        if not text:
            return ""

        text = str(text).strip()
        text = re.sub(r"^```(?:sql)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
        return text.strip()

    @staticmethod
    def _content_to_text(content: Any) -> str:
        if content is None:
            return ""

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict):
                    if "text" in part:
                        text_parts.append(str(part.get("text", "")))
                    elif "content" in part:
                        text_parts.append(str(part.get("content", "")))
                    else:
                        text_parts.append(str(part))
                else:
                    text_parts.append(str(part))
            return "".join(text_parts)

        return str(content)

    def _chat_non_thinking(
        self,
        messages: list[dict[str, str]],
        temperature: float,
    ) -> str:
        request_kwargs: dict[str, Any] = {
            "model": Config.MODELSCOPE_MODEL,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
            "top_p": Config.MODELSCOPE_TOP_P,
            "timeout": Config.TIMEOUT,
            "extra_body": {
                "enable_thinking": False,
                "top_k": Config.MODELSCOPE_TOP_K,
            },
        }

        resp = self.client.chat.completions.create(**request_kwargs)

        choices = getattr(resp, "choices", None)
        if not choices:
            raise RuntimeError("ModelScope returned empty choices in non-thinking mode")

        message = getattr(choices[0], "message", None)
        if message is None:
            raise RuntimeError("ModelScope returned empty message in non-thinking mode")

        content = getattr(message, "content", None)
        text = self._content_to_text(content)

        if not text.strip():
            raise RuntimeError("ModelScope returned empty content in non-thinking mode")

        return self._clean_output(text)

    def _chat_thinking(
        self,
        messages: list[dict[str, str]],
        temperature: float,
    ) -> str:
        request_kwargs: dict[str, Any] = {
            "model": Config.MODELSCOPE_MODEL,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            "top_p": Config.MODELSCOPE_TOP_P,
            "timeout": Config.TIMEOUT,
            "extra_body": {
                "enable_thinking": True,
                "top_k": Config.MODELSCOPE_TOP_K,
            },
        }

        response = self.client.chat.completions.create(**request_kwargs)

        answer_parts: list[str] = []
        reasoning_len = 0

        for chunk in response:
            choices = getattr(chunk, "choices", None)
            if not choices:
                continue

            delta = getattr(choices[0], "delta", None)
            if delta is None:
                continue

            reasoning_chunk = getattr(delta, "reasoning_content", None) or ""
            answer_chunk = getattr(delta, "content", None) or ""

            if reasoning_chunk:
                reasoning_len += len(reasoning_chunk)

            if answer_chunk:
                answer_parts.append(answer_chunk)

        final_answer = "".join(answer_parts).strip()

        if not final_answer:
            raise RuntimeError(
                f"ModelScope returned empty final answer in thinking mode; reasoning_len={reasoning_len}"
            )

        return self._clean_output(final_answer)

    def _chat(self, messages: list[dict[str, str]], temperature: float | None = None) -> str:
        try:
            final_temperature = Config.MODELSCOPE_TEMPERATURE if temperature is None else temperature

            if Config.MODELSCOPE_ENABLE_THINKING:
                return self._chat_thinking(
                    messages=messages,
                    temperature=final_temperature,
                )

            return self._chat_non_thinking(
                messages=messages,
                temperature=final_temperature,
            )

        except Exception as e:
            raise RuntimeError(f"ModelScope 调用失败: {e}") from e

    def _extract_first_sql(self, text: str) -> str:
        text = self._clean_output(text)

        select_match = re.search(r"\bSELECT\b", text, flags=re.IGNORECASE)
        if not select_match:
            return text

        sql = text[select_match.start():].strip()

        if ";" in sql:
            sql = sql[: sql.rfind(";") + 1].strip()

        return sql

    def call_decomposition(self, question: str, evidence: str, schema: str):
        try:
            prompt = build_node_activation_prompt(question, evidence, schema)
            raw = self._chat(
                [{"role": "system", "content": prompt}],
                temperature=Config.MODELSCOPE_DECOMPOSE_TEMPERATURE,
            )

            grads = {
                k.strip(): v.strip().replace("```", "")
                for k, v in re.findall(
                    r"(lev\d+-\d+)\s*[:：]\s*(.*?)(?=\s*lev\d+-\d+\s*[:：]|$)",
                    raw,
                    re.DOTALL,
                )
            }
            return grads, raw

        except Exception as e:
            raise RuntimeError(f"ModelScope (点亮节点) 请求失败: {e}") from e

    def call_supplement_workflow(self, question: str, evidence: str, schema: str) -> str:
        try:
            split_prompt = build_question_split_prompt(question)
            sub_questions = self._chat(
                [{"role": "system", "content": split_prompt}],
                temperature=Config.MODELSCOPE_QUESTION_SPLIT_TEMPERATURE,
            )

            if not sub_questions:
                raise RuntimeError("ModelScope 补充校准第一步无返回")

            extract_prompt = build_supp_extract_prompt(evidence, sub_questions, schema)
            raw = self._chat(
                [{"role": "system", "content": extract_prompt}],
                temperature=Config.MODELSCOPE_SUPP_EXTRACT_TEMPERATURE,
            )

            return raw

        except Exception as e:
            raise RuntimeError(f"ModelScope 补充请求失败: {e}") from e


    def call_draft_sql_workflow(
        self,
        question: str,
        evidence: str,
        relationship,
        new_schema: str,
        examples: str,
        column_value_hints: str = "",
        sql_dialect: str = "SQLite",
    ) -> str:
        try:
            messages = build_sql_generation_messages(
                question=question,
                evidence=evidence,
                relationship=relationship,
                new_schema=new_schema,
                examples=examples,
                column_value_hints=column_value_hints,
                sql_dialect=sql_dialect,
            )
            raw = self._chat(
                messages,
                temperature=Config.MODELSCOPE_SQL_TEMPERATURE,
            )
            return self._extract_first_sql(raw)
        except Exception as e:
            raise RuntimeError(f"ModelScope (生成Draft SQL) 请求失败: {e}") from e

    def call_corrected_workflow(
        self,
        question: str,
        evidence: str,
        relationship,
        new_schema: str,
        examples: str,
        column_value_hints: str = "",
        sql_dialect: str = "SQLite",
    ) -> str:
        try:
            messages = build_sql_generation_messages(
                question=question,
                evidence=evidence,
                relationship=relationship,
                new_schema=new_schema,
                examples=examples,
                column_value_hints=column_value_hints,
                sql_dialect=sql_dialect,
            )

            raw = self._chat(
                messages,
                temperature=Config.MODELSCOPE_SQL_TEMPERATURE,
            )

            sql = self._extract_first_sql(raw)
            return sql

        except Exception as e:
            raise RuntimeError(f"ModelScope (生成SQL) 请求失败: {e}") from e
