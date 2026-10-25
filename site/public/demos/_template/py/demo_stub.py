"""Stub entry module for the template demo."""


def analyse(text: str) -> dict[str, object]:
    return {"words": len(text.split()), "upper": text.upper()}
