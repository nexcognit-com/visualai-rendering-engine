import json
import logging
import re
import requests
from typing import List

import g4f
from loguru import logger
from openai import AzureOpenAI, OpenAI
from openai.types.chat import ChatCompletion

from app.config import config

_max_retries = 5
_DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
_DEPRECATED_GEMINI_MODELS = {"gemini-pro", "gemini-1.0-pro"}


def _normalize_text_response(content, llm_provider: str) -> str:
    # 不同 LLM SDK 在异常或被拦截场景下，可能返回 None、空字符串，
    # 甚至返回非字符串对象。这里统一做兜底校验，避免后续直接调用
    # `.replace()` 时抛出 `NoneType` 之类的属性错误。
    if content is None:
        raise ValueError(f"[{llm_provider}] returned empty text content")

    if not isinstance(content, str):
        raise TypeError(
            f"[{llm_provider}] returned non-text content: {type(content).__name__}"
        )

    content = content.strip()
    if not content:
        raise ValueError(f"[{llm_provider}] returned empty text content")

    return content.replace("\n", "")


def _extract_chat_completion_text(response, llm_provider: str) -> str:
    # OpenAI 兼容接口在异常场景下，可能返回没有 choices、
    # 或者 choices/message/content 为空的响应对象。
    # 这里统一做结构校验，避免出现 `NoneType is not subscriptable`
    # 这类底层属性访问错误。
    choices = getattr(response, "choices", None)
    if not choices:
        raise ValueError(f"[{llm_provider}] returned empty choices")

    first_choice = choices[0]
    message = getattr(first_choice, "message", None)
    if message is None:
        raise ValueError(f"[{llm_provider}] returned empty message")

    content = getattr(message, "content", None)
    return _normalize_text_response(content, llm_provider)


def _generate_response(prompt: str) -> str:
    try:
        content = ""
        llm_provider = config.app.get("llm_provider", "openai")
        logger.info(f"llm provider: {llm_provider}")
        if llm_provider == "g4f":
            model_name = config.app.get("g4f_model_name", "")
            if not model_name:
                model_name = "gpt-3.5-turbo-16k-0613"
            content = g4f.ChatCompletion.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
            )
        else:
            api_version = ""  # for azure
            if llm_provider == "moonshot":
                api_key = config.app.get("moonshot_api_key")
                model_name = config.app.get("moonshot_model_name")
                base_url = "https://api.moonshot.cn/v1"
            elif llm_provider == "ollama":
                # api_key = config.app.get("openai_api_key")
                api_key = "ollama"  # any string works but you are required to have one
                model_name = config.app.get("ollama_model_name")
                base_url = config.app.get("ollama_base_url", "")
                if not base_url:
                    base_url = "http://localhost:11434/v1"
            elif llm_provider == "openai":
                api_key = config.app.get("openai_api_key")
                model_name = config.app.get("openai_model_name")
                base_url = config.app.get("openai_base_url", "")
                if not base_url:
                    base_url = "https://api.openai.com/v1"
            elif llm_provider == "oneapi":
                api_key = config.app.get("oneapi_api_key")
                model_name = config.app.get("oneapi_model_name")
                base_url = config.app.get("oneapi_base_url", "")
            elif llm_provider == "azure":
                api_key = config.app.get("azure_api_key")
                model_name = config.app.get("azure_model_name")
                base_url = config.app.get("azure_base_url", "")
                api_version = config.app.get("azure_api_version", "2024-02-15-preview")
            elif llm_provider == "gemini":
                api_key = config.app.get("gemini_api_key")
                model_name = config.app.get("gemini_model_name")
                base_url = config.app.get("gemini_base_url", "")
                # Gemini 旧模型名已经陆续下线，这里自动兼容历史配置，
                # 避免用户沿用旧值时直接收到 404。
                if not model_name:
                    model_name = _DEFAULT_GEMINI_MODEL
                elif model_name in _DEPRECATED_GEMINI_MODELS:
                    logger.warning(
                        f"gemini model '{model_name}' is deprecated, fallback to '{_DEFAULT_GEMINI_MODEL}'"
                    )
                    model_name = _DEFAULT_GEMINI_MODEL
            elif llm_provider == "qwen":
                api_key = config.app.get("qwen_api_key")
                model_name = config.app.get("qwen_model_name")
                base_url = "***"
            elif llm_provider == "cloudflare":
                api_key = config.app.get("cloudflare_api_key")
                model_name = config.app.get("cloudflare_model_name")
                account_id = config.app.get("cloudflare_account_id")
                base_url = "***"
            elif llm_provider == "minimax":
                api_key = config.app.get("minimax_api_key")
                model_name = config.app.get("minimax_model_name")
                base_url = config.app.get("minimax_base_url", "")
                if not base_url:
                    base_url = "https://api.minimax.io/v1"
            elif llm_provider == "deepseek":
                api_key = config.app.get("deepseek_api_key")
                model_name = config.app.get("deepseek_model_name")
                base_url = config.app.get("deepseek_base_url")
                if not base_url:
                    base_url = "https://api.deepseek.com"
            elif llm_provider == "modelscope":
                api_key = config.app.get("modelscope_api_key")
                model_name = config.app.get("modelscope_model_name")
                base_url = config.app.get("modelscope_base_url")
                if not base_url:
                    base_url = "https://api-inference.modelscope.cn/v1/"
            elif llm_provider == "ernie":
                api_key = config.app.get("ernie_api_key")
                secret_key = config.app.get("ernie_secret_key")
                base_url = config.app.get("ernie_base_url")
                model_name = "***"
                if not secret_key:
                    raise ValueError(
                        f"{llm_provider}: secret_key is not set, please set it in the config.toml file."
                    )
            elif llm_provider == "pollinations":
                try:
                    base_url = config.app.get("pollinations_base_url", "")
                    if not base_url:
                        base_url = "https://text.pollinations.ai/openai"
                    model_name = config.app.get("pollinations_model_name", "openai-fast")
                   
                    # Prepare the payload
                    payload = {
                        "model": model_name,
                        "messages": [
                            {"role": "user", "content": prompt}
                        ],
                        "seed": 101  # Optional but helps with reproducibility
                    }
                    
                    # Optional parameters if configured
                    if config.app.get("pollinations_private"):
                        payload["private"] = True
                    if config.app.get("pollinations_referrer"):
                        payload["referrer"] = config.app.get("pollinations_referrer")
                    
                    headers = {
                        "Content-Type": "application/json"
                    }
                    
                    # Make the API request
                    response = requests.post(base_url, headers=headers, json=payload)
                    response.raise_for_status()
                    result = response.json()
                    
                    if result and "choices" in result and len(result["choices"]) > 0:
                        content = result["choices"][0]["message"]["content"]
                        return _normalize_text_response(content, llm_provider)
                    else:
                        raise Exception(f"[{llm_provider}] returned an invalid response format")
                        
                except requests.exceptions.RequestException as e:
                    raise Exception(f"[{llm_provider}] request failed: {str(e)}")
                except Exception as e:
                    raise Exception(f"[{llm_provider}] error: {str(e)}")

            if llm_provider not in ["pollinations", "ollama"]:  # Skip validation for providers that don't require API key
                if not api_key:
                    raise ValueError(
                        f"{llm_provider}: api_key is not set, please set it in the config.toml file."
                    )
                if not model_name:
                    raise ValueError(
                        f"{llm_provider}: model_name is not set, please set it in the config.toml file."
                    )
                if not base_url and llm_provider not in ["gemini"]:
                    raise ValueError(
                        f"{llm_provider}: base_url is not set, please set it in the config.toml file."
                    )

            if llm_provider == "qwen":
                import dashscope
                from dashscope.api_entities.dashscope_response import GenerationResponse

                dashscope.api_key = api_key
                response = dashscope.Generation.call(
                    model=model_name, messages=[{"role": "user", "content": prompt}]
                )
                if response:
                    if isinstance(response, GenerationResponse):
                        status_code = response.status_code
                        if status_code != 200:
                            raise Exception(
                                f'[{llm_provider}] returned an error response: "{response}"'
                            )

                        content = response["output"]["text"]
                        return content.replace("\n", "")
                    else:
                        raise Exception(
                            f'[{llm_provider}] returned an invalid response: "{response}"'
                        )
                else:
                    raise Exception(f"[{llm_provider}] returned an empty response")

            if llm_provider == "gemini":
                import google.generativeai as genai

                if not base_url:
                    genai.configure(api_key=api_key, transport="rest")
                else:
                    genai.configure(api_key=api_key, transport="rest", client_options={'api_endpoint': base_url})

                generation_config = {
                    "temperature": 0.5,
                    "top_p": 1,
                    "top_k": 1,
                    "max_output_tokens": 2048,
                }

                safety_settings = [
                    {
                        "category": "HARM_CATEGORY_HARASSMENT",
                        "threshold": "BLOCK_ONLY_HIGH",
                    },
                    {
                        "category": "HARM_CATEGORY_HATE_SPEECH",
                        "threshold": "BLOCK_ONLY_HIGH",
                    },
                    {
                        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        "threshold": "BLOCK_ONLY_HIGH",
                    },
                    {
                        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                        "threshold": "BLOCK_ONLY_HIGH",
                    },
                ]

                model = genai.GenerativeModel(
                    model_name=model_name,
                    generation_config=generation_config,
                    safety_settings=safety_settings,
                )

                try:
                    response = model.generate_content(prompt)
                    candidates = response.candidates
                    generated_text = candidates[0].content.parts[0].text
                except (AttributeError, IndexError) as e:
                    print("Gemini Error:", e)
                    raise ValueError(f"[{llm_provider}] returned invalid response content")

                return _normalize_text_response(generated_text, llm_provider)

            if llm_provider == "cloudflare":
                response = requests.post(
                    f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model_name}",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a friendly assistant",
                            },
                            {"role": "user", "content": prompt},
                        ]
                    },
                )
                result = response.json()
                logger.info(result)
                return _normalize_text_response(result["result"]["response"], llm_provider)

            if llm_provider == "ernie":
                response = requests.post(
                    "https://aip.baidubce.com/oauth/2.0/token", 
                    params={
                        "grant_type": "client_credentials",
                        "client_id": api_key,
                        "client_secret": secret_key,
                    }
                )
                access_token = response.json().get("access_token")
                url = f"{base_url}?access_token={access_token}"

                payload = json.dumps(
                    {
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.5,
                        "top_p": 0.8,
                        "penalty_score": 1,
                        "disable_search": False,
                        "enable_citation": False,
                        "response_format": "text",
                    }
                )
                headers = {"Content-Type": "application/json"}

                response = requests.request(
                    "POST", url, headers=headers, data=payload
                ).json()
                return _normalize_text_response(response.get("result"), llm_provider)

            if llm_provider == "azure":
                client = AzureOpenAI(
                    api_key=api_key,
                    api_version=api_version,
                    azure_endpoint=base_url,
                )

            if llm_provider == "modelscope":
                content = ''
                client = OpenAI(
                    api_key=api_key,
                    base_url=base_url,
                )
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    extra_body={"enable_thinking": False},
                    stream=True
                )
                if response:
                    for chunk in response:
                        if not chunk.choices:
                            continue
                        delta = chunk.choices[0].delta
                        if delta and delta.content:
                            content += delta.content
                    
                    if not content.strip():
                        raise ValueError("Empty content in stream response")
                    
                    return _normalize_text_response(content, llm_provider)
                else:
                    raise Exception(f"[{llm_provider}] returned an empty response")

            else:
                client = OpenAI(
                    api_key=api_key,
                    base_url=base_url,
                )

            response = client.chat.completions.create(
                model=model_name, messages=[{"role": "user", "content": prompt}]
            )
            if response:
                if isinstance(response, ChatCompletion):
                    return _extract_chat_completion_text(response, llm_provider)
                else:
                    raise Exception(
                        f'[{llm_provider}] returned an invalid response: "{response}", please check your network '
                        f"connection and try again."
                    )
            else:
                raise Exception(
                    f"[{llm_provider}] returned an empty response, please check your network connection and try again."
                )

        return _normalize_text_response(content, llm_provider)
    except Exception as e:
        return f"Error: {str(e)}"


def generate_script(
    video_subject: str, language: str = "", paragraph_number: int = 1
) -> str:
    prompt = f"""
# Role: Video Script Generator

## Goals:
Generate a script for a video, depending on the subject of the video.

## Constrains:
1. the script is to be returned as a string with the specified number of paragraphs.
2. do not under any circumstance reference this prompt in your response.
3. get straight to the point, don't start with unnecessary things like, "welcome to this video".
4. you must not include any type of markdown or formatting in the script, never use a title.
5. only return the raw content of the script.
6. do not include "voiceover", "narrator" or similar indicators of what should be spoken at the beginning of each paragraph or line.
7. you must not mention the prompt, or anything about the script itself. also, never talk about the amount of paragraphs or lines. just write the script.
8. respond in the same language as the video subject.

# Initialization:
- video subject: {video_subject}
- number of paragraphs: {paragraph_number}
""".strip()
    if language:
        prompt += f"\n- language: {language}"

    final_script = ""
    logger.info(f"subject: {video_subject}")

    def format_response(response):
        # Clean the script
        # Remove asterisks, hashes
        response = response.replace("*", "")
        response = response.replace("#", "")

        # Remove markdown syntax
        response = re.sub(r"\[.*\]", "", response)
        response = re.sub(r"\(.*\)", "", response)

        # Split the script into paragraphs
        paragraphs = response.split("\n\n")

        # Select the specified number of paragraphs
        # selected_paragraphs = paragraphs[:paragraph_number]

        # Join the selected paragraphs into a single string
        return "\n\n".join(paragraphs)

    for i in range(_max_retries):
        try:
            response = _generate_response(prompt=prompt)
            if response:
                final_script = format_response(response)
            else:
                logging.error("gpt returned an empty response")

            # g4f may return an error message
            if final_script and "当日额度已消耗完" in final_script:
                raise ValueError(final_script)

            if final_script:
                break
        except Exception as e:
            logger.error(f"failed to generate script: {e}")

        if i < _max_retries:
            logger.warning(f"failed to generate video script, trying again... {i + 1}")
    if "Error: " in final_script:
        logger.error(f"failed to generate video script: {final_script}")
    else:
        logger.success(f"completed: \n{final_script}")
    return final_script.strip()


# ---------------------------------------------------------------------------
# Spec 015 — Mode 5 quality: research-then-write pass
# ---------------------------------------------------------------------------


def research_topic(
    topic: str,
    *,
    max_results: int = 5,
    region: str = "us-en",
    timeout_s: float = 8.0,
) -> List[str]:
    """Pull short factual snippets about ``topic`` from a web search engine.

    Used by :mod:`app.services.modes.faceless` to ground the generated
    script in current facts instead of relying on the LLM's training-time
    knowledge alone.

    Returns up to ``max_results`` snippet strings (title + body, truncated).
    Returns an empty list on any failure (network down, search lib missing,
    rate limit) so the caller can degrade gracefully to ungrounded
    generation.

    Provider: DuckDuckGo via the ``ddgs`` package — no API key required.
    """
    snippets: List[str] = []
    try:
        from ddgs import DDGS  # type: ignore[import-not-found]
    except ImportError:
        logger.warning("research_topic: ddgs not installed; returning [] (run `pip install ddgs`)")
        return []

    try:
        with DDGS(timeout=timeout_s) as d:
            results = list(d.text(topic, max_results=max_results, region=region))
    except Exception as exc:  # noqa: BLE001 — best-effort
        logger.warning(f"research_topic: search failed for {topic!r}: {exc}")
        return []

    for r in results:
        title = (r.get("title") or "").strip()
        body = (r.get("body") or "").strip()
        if not (title or body):
            continue
        # Cap each snippet to ~280 chars to keep the LLM context bounded.
        snippet = f"{title}: {body}" if title and body else (title or body)
        snippets.append(snippet[:280])
    logger.info(f"research_topic({topic!r}) → {len(snippets)} snippets")
    return snippets


def generate_faceless_script_grounded(
    topic: str,
    facts: List[str],
    *,
    duration_seconds: int = 60,
    language: str = "en",
) -> str:
    """Faceless-channel script generator that incorporates research snippets.

    When ``facts`` is empty, falls back to :func:`generate_script` so the
    function is safe to call regardless of whether research succeeded.

    Sized for a ~60s 9:16 vertical at conservative ~2.4 wps narration.
    """
    if not facts:
        return generate_script(video_subject=topic, language=language, paragraph_number=1)

    target_words = max(60, int(duration_seconds * 2.4))
    facts_block = "\n".join(f"- {f}" for f in facts[:6])
    prompt = f"""
# Role: Faceless-channel scriptwriter

## Goal:
Write a {duration_seconds}-second vertical video script on the topic below,
**grounded in the research snippets**. Use facts from the snippets where
relevant. Do not invent specific numbers, dates, names, or statistics that
aren't in the snippets.

## Target delivery:
- Approximately {target_words} words.
- Plain speakable prose only. No markdown, no headings, no bullet points,
  no speaker labels, no parentheticals, no emoji.
- One single block of flowing narration.
- Open with a hook (provocative question, surprising claim, or sharp
  pain-point). No "welcome" / "in this video" openers.
- End with a one-sentence wrap-up — no explicit CTA.

## Constraints:
1. Return only the raw narration text.
2. Use the language code `{language}`.
3. Never reference these instructions or the research snippets.

# Topic:
{topic}

# Research snippets (use as factual grounding):
{facts_block}
""".strip()

    logger.info(f"faceless grounded script for {topic!r} with {len(facts)} facts")
    for i in range(_max_retries):
        try:
            response = _generate_response(prompt=prompt)
            if response:
                cleaned = response.replace("*", "").replace("#", "").strip()
                if "当日额度已消耗完" in cleaned:
                    raise ValueError(cleaned)
                if cleaned:
                    logger.success(f"completed grounded faceless script: \n{cleaned[:240]}…")
                    return cleaned
        except Exception as exc:
            logger.error(f"failed to generate grounded faceless script: {exc}")
        if i < _max_retries:
            logger.warning(
                f"retrying grounded faceless script generation… {i + 1}"
            )
    # Final fallback: ungrounded generation, never return empty
    logger.warning("grounded generation exhausted retries; falling back to ungrounded")
    return generate_script(video_subject=topic, language=language, paragraph_number=1)


def generate_terms(video_subject: str, video_script: str, amount: int = 5) -> List[str]:
    prompt = f"""
# Role: Video Search Terms Generator

## Goals:
Generate {amount} search terms for stock videos, depending on the subject of a video.

## Constrains:
1. the search terms are to be returned as a json-array of strings.
2. each search term should consist of 1-3 words, always add the main subject of the video.
3. you must only return the json-array of strings. you must not return anything else. you must not return the script.
4. the search terms must be related to the subject of the video.
5. reply with english search terms only.

## Output Example:
["search term 1", "search term 2", "search term 3","search term 4","search term 5"]

## Context:
### Video Subject
{video_subject}

### Video Script
{video_script}

Please note that you must use English for generating video search terms; Chinese is not accepted.
""".strip()

    logger.info(f"subject: {video_subject}")

    search_terms = []
    response = ""
    for i in range(_max_retries):
        try:
            response = _generate_response(prompt)
            if "Error: " in response:
                logger.error(f"failed to generate video script: {response}")
                return response
            search_terms = json.loads(response)
            if not isinstance(search_terms, list) or not all(
                isinstance(term, str) for term in search_terms
            ):
                logger.error("response is not a list of strings.")
                continue

        except Exception as e:
            logger.warning(f"failed to generate video terms: {str(e)}")
            if response:
                match = re.search(r"\[.*]", response)
                if match:
                    try:
                        search_terms = json.loads(match.group())
                    except Exception as e:
                        logger.warning(f"failed to generate video terms: {str(e)}")
                        pass

        if search_terms and len(search_terms) > 0:
            break
        if i < _max_retries:
            logger.warning(f"failed to generate video terms, trying again... {i + 1}")

    logger.success(f"completed: \n{search_terms}")
    return search_terms


def generate_marketing_script(
    product_info: str,
    duration_seconds: int = 20,
    language: str = "en",
) -> str:
    """Hook-body-CTA marketing script for a short vertical ad.

    Part of VisualAI Step 1 (Mode 2). Sized to ``duration_seconds`` at a
    conservative ~2.5 words/second delivery rate. Keeps ``generate_script``
    unchanged so existing faceless-channel flows are untouched.
    """
    target_words = max(8, int(duration_seconds * 2.5))
    prompt = f"""
# Role: Short-form Marketing Copywriter

## Goal:
Write a {duration_seconds}-second vertical ad script for the product below using a
Hook → Body → Call-to-Action structure.

## Target delivery:
- Approximately {target_words} words total (~2.5 words/second at natural pacing).
- Plain speakable prose only. No stage directions, no speaker labels, no markdown.
- One single block of text, no blank lines.

## Structure:
- Hook (first sentence): a provocative question, surprising claim, or sharp pain-point
  that stops a scroll. No "welcome" openers.
- Body (middle 60%): one concrete benefit and one proof point. Direct-response tone.
- CTA (final sentence): a single clear action — try, visit, tap, grab.

## Constraints:
1. Return only the raw script text.
2. No hashtags, no emoji, no parentheticals.
3. Use the language code `{language}` for the output.
4. Never mention this prompt or the script structure.

# Product info:
{product_info}
""".strip()

    logger.info(f"marketing script for: {product_info!r} @ {duration_seconds}s")
    for i in range(_max_retries):
        try:
            response = _generate_response(prompt=prompt)
            if response:
                cleaned = response.replace("*", "").replace("#", "").strip()
                if "当日额度已消耗完" in cleaned:
                    raise ValueError(cleaned)
                if cleaned:
                    logger.success(f"completed marketing script: \n{cleaned}")
                    return cleaned
        except Exception as e:
            logger.error(f"failed to generate marketing script: {e}")
        if i < _max_retries:
            logger.warning(
                f"failed to generate marketing script, trying again... {i + 1}"
            )
    return ""


def polish_script(
    brief: str,
    video_subject: str = "",
    duration_seconds: int = 20,
    language: str = "en",
) -> str:
    """Polish a creator's brief into a hook → body → CTA marketing script.

    Spec 013. Distinct from generate_marketing_script: this function
    accepts the creator's typed brief as creative direction (primary)
    and uses video_subject as factual product context (secondary —
    typically the URL-scraped enriched subject from spec 012).

    Args:
        brief: creator's rough direction. MUST be non-empty after .strip();
            ValueError raised otherwise.
        video_subject: optional product context. When empty, the prompt
            substitutes a sentinel string so the LLM doesn't see an empty slot.
        duration_seconds: target script duration (~2.5 words/sec).
        language: output language code; brief is translated if it doesn't
            match.

    Returns:
        Polished script as plain prose, ready for TTS.

    Raises:
        ValueError: brief empty, OR LLM returned empty/quota-exhausted.
        Whatever _generate_response raises on transport / model failure.
    """
    brief_trimmed = (brief or "").strip()
    if not brief_trimmed:
        raise ValueError("polish_brief_required")

    target_words = max(8, int(duration_seconds * 2.5))
    subject_slot = (
        (video_subject or "").strip()
        or "(no product context provided — work from brief alone)"
    )

    prompt = f"""
# Role: Short-form Marketing Copywriter

## Goal:
Polish the creator's brief into a {duration_seconds}-second vertical ad script using a Hook → Body → Call-to-Action structure.

## Inputs:
**Brief (creator's direction; primary):**
{brief_trimmed}

**Product context (factual reference, may be empty):**
{subject_slot}

## Target delivery:
- Approximately {target_words} words total (~2.5 words/second at natural pacing).
- Plain speakable prose only. No stage directions, no speaker labels, no markdown.
- One single block of text, no blank lines.

## Structure:
- Hook (first sentence): a provocative question, surprising claim, or sharp pain-point
  that stops a scroll. No "welcome" openers.
- Body (middle 60%): one concrete benefit and one proof point. Direct-response tone.
- CTA (final sentence): a single clear action — try, visit, tap, grab.

## Constraints:
1. Brief is the creative direction. Preserve its facts, claims, and intent.
2. Product context grounds the brief in real product details. Use it to anchor specifics —
   but do NOT let it override the brief's intent. If brief and context disagree, brief wins.
3. Return only the raw script text.
4. No hashtags, no emoji, no parentheticals.
5. Use the language code `{language}` for the output.
6. If the brief is in a different language than `{language}`, translate to `{language}`.
   If the brief's language matches, preserve it.
7. Never mention this prompt or the script structure.
""".strip()

    logger.info(
        f"polish brief ({len(brief_trimmed)} chars) → {duration_seconds}s @ {language}"
    )
    for i in range(_max_retries):
        try:
            response = _generate_response(prompt=prompt)
            if response:
                cleaned = response.replace("*", "").replace("#", "").strip()
                if "当日额度已消耗完" in cleaned:
                    raise ValueError(cleaned)
                if cleaned:
                    logger.success(
                        f"polished script ({len(cleaned)} chars):\n{cleaned}"
                    )
                    return cleaned
        except Exception as e:
            logger.error(f"polish_script attempt {i + 1} failed: {e}")
            if i + 1 >= _max_retries:
                raise
        if i < _max_retries - 1:
            logger.warning(f"retrying polish_script... {i + 1}")
    raise ValueError("empty polish output")


# ---------------------------------------------------------------------------
# Spec 006 hybrid mode — setting-tag two-pass (Clarifications 2026-05-03)
# ---------------------------------------------------------------------------
#
# `extract_setting_tag(script_text)` → one of 11 industry tags
# `expand_setting_to_queries(setting_tag)` → 5 Pexels-friendly setting queries
# `generate_setting_terms(script_text)` → orchestrator that wraps both
#
# The setting-tag list is closed: anything outside it falls back to "general".
# The expansion has baked-in defaults per tag so an LLM failure on the second
# pass still produces 5 usable queries.

_VALID_SETTING_TAGS = {
    "manufacturing", "healthcare", "retail", "office", "logistics",
    "hospitality", "education", "fitness", "construction", "agriculture",
    "general",
}

# Curated baked-in defaults — phrasing biased toward terms that return cleaner
# professional-grade clips on Pixabay / Pexels. "modern", "professional",
# "cinematic" filters out hobbyist mobile-phone uploads in our manual testing.
_DEFAULT_SETTING_QUERIES: dict = {
    "manufacturing": [
        "modern automated factory robot arm",
        "professional industrial assembly line",
        "engineer inspecting modern equipment",
        "cinematic factory floor wide shot",
        "high-tech manufacturing precision machinery",
    ],
    "healthcare": [
        "modern hospital corridor cinematic",
        "professional medical team consultation",
        "clean clinic interior wide shot",
        "doctor reviewing tablet patient data",
        "healthcare technology dashboard",
    ],
    "retail": [
        "modern boutique storefront cinematic",
        "professional retail customer experience",
        "elegant shopping mall interior",
        "store associate helping customer professional",
        "high-end retail product display",
    ],
    "office": [
        "modern open-plan office cinematic",
        "professional team meeting glass conference",
        "executive working laptop minimal desk",
        "business team handshake professional",
        "corporate city skyline office window",
    ],
    "logistics": [
        "modern logistics warehouse cinematic",
        "professional delivery driver scanning",
        "shipping container port aerial",
        "automated warehouse robotics",
        "courier service dispatch professional",
    ],
    "hospitality": [
        "modern hotel reception cinematic",
        "professional restaurant kitchen chef",
        "elegant hotel lobby ambient",
        "barista preparing coffee professional",
        "luxury hospitality dining experience",
    ],
    "education": [
        "modern classroom cinematic wide shot",
        "professional teacher engaging students",
        "university lecture hall elegant",
        "student studying laptop modern library",
        "education technology classroom",
    ],
    "fitness": [
        "modern gym cinematic wide shot",
        "professional trainer coaching client",
        "yoga studio minimalist elegant",
        "athlete running treadmill cinematic",
        "fitness equipment professional clean",
    ],
    "construction": [
        "modern construction site cinematic",
        "professional engineer reviewing blueprints",
        "crane high-rise building aerial",
        "construction crew safety equipment",
        "architect inspecting site modern",
    ],
    "agriculture": [
        "modern farm cinematic wide shot",
        "professional tractor harvesting field",
        "greenhouse precision irrigation",
        "farmer inspecting crops technology",
        "agricultural drone field overview",
    ],
    "general": [
        "modern professional team collaboration",
        "business handshake cinematic",
        "city skyline aerial professional",
        "executive working modern office",
        "corporate team meeting elegant",
    ],
}


def extract_setting_tag(script_text: str) -> str:
    """Pass 1 of the two-pass setting flow. Returns one of 11 industry tags.

    Falls back to "general" on empty input, LLM failure, or out-of-allowlist.
    """
    if not script_text or not script_text.strip():
        return "general"

    prompt = f"""You are picking ONE industry setting that best matches the following marketing script.

Script:
\"\"\"
{script_text.strip()}
\"\"\"

Choose EXACTLY ONE tag from this closed list — no other answer is valid:
- manufacturing
- healthcare
- retail
- office
- logistics
- hospitality
- education
- fitness
- construction
- agriculture
- general

Respond with the tag and nothing else. Lowercase. No punctuation. No explanation."""

    try:
        response = _generate_response(prompt=prompt)
    except Exception as exc:
        logger.warning(f"extract_setting_tag LLM call failed: {exc}; falling back to 'general'")
        return "general"

    tag = (response or "").strip().lower()
    # Strip surrounding noise (quotes, periods, commas, backticks, whitespace)
    # in any order — the LLM may emit `"healthcare".` or `'healthcare'` etc.
    tag = re.sub(r'^[\s"\'`.,]+|[\s"\'`.,]+$', "", tag)
    if tag in _VALID_SETTING_TAGS:
        logger.info(f"setting tag resolved: {tag}")
        return tag
    logger.warning(f"setting tag '{tag}' not in allowlist; falling back to 'general'")
    return "general"


def expand_setting_to_queries(setting_tag: str) -> list:
    """Pass 2: returns exactly 5 Pexels-friendly queries for the given tag.

    Tries the LLM for variety; on any failure or malformed JSON, returns the
    baked-in default-queries list for that tag.
    """
    safe_tag = setting_tag if setting_tag in _VALID_SETTING_TAGS else "general"
    defaults = _DEFAULT_SETTING_QUERIES[safe_tag]

    prompt = f"""You are generating 5 short search queries for a stock-footage library (Pixabay / Pexels-style).

Industry setting: {safe_tag}

Each query must:
- describe a CONCRETE visual scene (not an abstract concept).
- focus on people, places, or actions in the {safe_tag} setting.
- be 3 to 7 words long.
- be different from the others.
- be the kind of phrase a stock library would index against.

Quality bias — INCLUDE at least one of these descriptors in each query to bias
the stock library toward agency-grade footage and away from hobbyist uploads:
"modern", "professional", "cinematic", "elegant", "high-tech", "wide shot",
"aerial", "minimalist", "corporate". Pick the descriptor that best fits the
scene; don't stack more than one per query.

Respond with ONLY a JSON array of exactly 5 strings, like:
["modern factory robot arm cinematic", "professional engineer inspecting machinery", "automated assembly line wide shot", "high-tech quality control inspection", "warehouse aerial forklift operations"]

No prose, no commentary, no markdown — just the JSON array."""

    try:
        response = _generate_response(prompt=prompt)
    except Exception as exc:
        logger.warning(f"expand_setting_to_queries LLM call failed: {exc}; using defaults")
        return list(defaults)

    raw = (response or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()
    queries = None
    try:
        queries = json.loads(raw)
    except Exception:
        match = re.search(r"\[.*?\]", raw, re.DOTALL)
        if match:
            try:
                queries = json.loads(match.group())
            except Exception:
                queries = None

    if not isinstance(queries, list) or len(queries) < 1:
        logger.warning("expand_setting_to_queries: malformed LLM response; using defaults")
        return list(defaults)

    cleaned = [str(q).strip() for q in queries if isinstance(q, (str, int, float))]
    cleaned = [q for q in cleaned if q]
    if len(cleaned) < 5:
        cleaned = (cleaned + list(defaults))[:5]
    return cleaned[:5]


def generate_setting_terms(script_text: str):
    """Orchestrator for the two-pass flow used by spec 006 hybrid mode.

    Returns (setting_tag, queries[5]). Always returns a usable tuple — on
    any internal failure falls back to ("general", general_queries).
    """
    try:
        tag = extract_setting_tag(script_text)
        queries = expand_setting_to_queries(tag)
        return tag, queries
    except Exception as exc:
        logger.error(f"generate_setting_terms top-level failure: {exc}; using general defaults")
        return "general", list(_DEFAULT_SETTING_QUERIES["general"])


if __name__ == "__main__":
    video_subject = "生命的意义是什么"
    script = generate_script(
        video_subject=video_subject, language="zh-CN", paragraph_number=1
    )
    print("######################")
    print(script)
    search_terms = generate_terms(
        video_subject=video_subject, video_script=script, amount=5
    )
    print("######################")
    print(search_terms)
    
