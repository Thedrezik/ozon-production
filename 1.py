from pathlib import Path
import re


TASKS_DIR = Path("tasks")


def choose_model(complexity: str) -> tuple[str, str]:
    value = complexity.strip().upper()

    if value == "LOW":
        return "GPT-6 Luna", "Medium"

    if value == "MEDIUM":
        return "GPT-6 Sol", "Low"

    if "HIGH" in value:
        return "GPT-6 Sol", "Medium"

    raise ValueError(f"Unknown complexity: {complexity}")


def update_task(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")

    complexity_match = re.search(
        r"^complexity:\s*(.+?)\s*$",
        text,
        flags=re.MULTILINE | re.IGNORECASE,
    )

    if not complexity_match:
        print(f"[SKIP] {path.name}: no complexity field")
        return False

    complexity = complexity_match.group(1).strip()
    model, reasoning = choose_model(complexity)

    original = text

    # Update recommended_model
    if re.search(
        r"^recommended_model:",
        text,
        flags=re.MULTILINE | re.IGNORECASE,
    ):
        text = re.sub(
            r"^recommended_model:\s*.*$",
            f"recommended_model: {model}",
            text,
            flags=re.MULTILINE | re.IGNORECASE,
        )
    else:
        # Insert after complexity if field is missing
        text = re.sub(
            r"(^complexity:\s*.*$)",
            rf"\1\nrecommended_model: {model}",
            text,
            count=1,
            flags=re.MULTILINE | re.IGNORECASE,
        )

    # Update reasoning
    if re.search(
        r"^reasoning:",
        text,
        flags=re.MULTILINE | re.IGNORECASE,
    ):
        text = re.sub(
            r"^reasoning:\s*.*$",
            f"reasoning: {reasoning}",
            text,
            flags=re.MULTILINE | re.IGNORECASE,
        )
    else:
        text = re.sub(
            r"(^recommended_model:\s*.*$)",
            rf"\1\nreasoning: {reasoning}",
            text,
            count=1,
            flags=re.MULTILINE | re.IGNORECASE,
        )

    if text == original:
        print(f"[OK]   {path.name}: already correct")
        return False

    path.write_text(text, encoding="utf-8", newline="\n")

    print(
        f"[EDIT] {path.name}: "
        f"{complexity} -> {model} / {reasoning}"
    )
    return True


def main():
    if not TASKS_DIR.exists():
        raise SystemExit(
            f"Folder '{TASKS_DIR}' not found. "
            "Run this script from the repository root."
        )

    updated = 0
    missing = []

    for number in range(1, 36):
        matches = sorted(TASKS_DIR.glob(f"{number:03d}-*.md"))

        if not matches:
            missing.append(number)
            continue

        if len(matches) > 1:
            print(
                f"[WARN] Task {number:03d}: "
                f"found multiple files: "
                f"{', '.join(p.name for p in matches)}"
            )

        for path in matches:
            if update_task(path):
                updated += 1

    print()
    print("Done.")
    print(f"Updated files: {updated}")

    if missing:
        print(
            "Missing task numbers: "
            + ", ".join(f"{n:03d}" for n in missing)
        )


if __name__ == "__main__":
    main()