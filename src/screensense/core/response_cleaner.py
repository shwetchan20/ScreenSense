from __future__ import annotations

import re


_REMOVE_PHRASES = [
    "On the screen, I see",
    "I can see that",
    "I see that",
    "Based on the screen",
    "As your AI assistant",
    "I notice that",
    "It appears that",
    "I would recommend",
    "Please note that",
    "I am here to help",
    "Ready to assist",
    "How can I help",
    "Is there anything",
    "As an AI",
    "Certainly!",
    "Sure!",
    "Great!",
    "Of course!",
]

_REPLACE_PREFIXES = [
    "I have detected",
    "I would suggest",
    "It seems like",
]


def clean_response(text: str) -> str:
    if not text:
        return ""

    # Normalize simple markdown lists/headings first.
    text = remove_lists(text)

    # Split into sentences first
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())

    good_sentences: list[str] = []
    bad_starts = [
        "hello",
        "hi ",
        "hey ",
        "hi,",
        "hello,",
        "how can i",
        "i am here",
        "i am aria",
        "i can help",
        "sure",
        "certainly",
        "of course",
        "great",
        "ready to",
        "is there anything",
        "what would you",
    ]
    bad_contains = [
        "it seems like",
        "it appears that",
        "let's break down",
        "in this section",
        "here's what",
        "here is what",
        "we can see that",
        "the output appears to be",
        "this looks like",
        "screen monitoring tool",
    ]

    for sentence in sentences:
        low = sentence.lower().strip()

        # Skip greeting sentences entirely
        if any(low.startswith(b) for b in bad_starts):
            continue

        # Skip obvious markdown artifacts / headings
        if "##" in sentence:
            continue
        if sentence.strip().startswith(("#", "*", "-", "•")):
            continue

        # Skip analytic/meta sentences we don't want ARIA to speak
        if any(p in low for p in bad_contains):
            continue

        # Skip question sentences
        if sentence.strip().endswith("?"):
            continue

        # Skip very short fragments
        if len(sentence.strip()) < 8:
            continue

        good_sentences.append(sentence.strip())

    # Take first 2 good sentences
    result = " ".join(good_sentences[:2]).strip()

    # If nothing survived, return safe fallback
    if not result:
        return "screen context loading."

    # Remove exclamation marks
    result = result.replace("!", ".")

    # Clamp overly long rambles
    if len(result) > 200:
        result = result[:197].rstrip() + "..."

    return result


def clean_response_proactive(text: str) -> str:
    cleaned = clean_response(text)
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    return " ".join(sentences[:2]).strip()


def remove_lists(text: str) -> str:
    lines = text.split("\n")
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^\d+\.", stripped):
            content = re.sub(r"^\d+\.\s*", "", stripped)
            cleaned.append(content)
        elif stripped.startswith(("-", "*", "•", "–")):
            content = stripped.lstrip("-*•– ")
            cleaned.append(content)
        else:
            cleaned.append(line)
    return "\n".join(cleaned).strip()
