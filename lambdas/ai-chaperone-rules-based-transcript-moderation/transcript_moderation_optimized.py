import csv
import re
import json
import ahocorasick
from dataclasses import dataclass, asdict
from typing import List, Dict


@dataclass
class Utterance:
    speaker: str
    text: str
    start_time: str
    end_time: str


@dataclass
class Violation:
    keyword: str
    speaker: str
    text: str
    timestamp: str
    categories: List[str]
    severity: str


class KeywordMatcher:
    def __init__(self, keyword_data: List[Dict]):
        self.single_words = {}
        self.phrases = {}

        # Initialize Aho-Corasick automaton for all keywords
        self.automaton = ahocorasick.Automaton()

        for item in keyword_data:
            keyword = item.get("keyword", "")
            if keyword and keyword.strip():
                normalized = keyword.lower().strip()
                data = {
                    "categories": item.get("categories", []),
                    "severity": item.get("severity", "LOW"),
                    "original": keyword,
                }

                if " " in normalized:
                    self.phrases[normalized] = data
                    # Add phrase to automaton
                    self.automaton.add_word(normalized, (normalized, data, "phrase"))
                else:
                    self.single_words[normalized] = data
                    # For single words, we'll use Aho-Corasick with boundary checking
                    self.automaton.add_word(normalized, (normalized, data, "word"))

        # Build the automaton
        self.automaton.make_automaton()

        # Pre-compile regex for word boundary checking
        self.word_boundary_pattern = re.compile(r"[a-zA-Z0-9-]")

        print(
            f"KeywordMatcher initialized with {len(self.single_words)} single words and {len(self.phrases)} phrases"
        )
        print(f"Aho-Corasick automaton built with {len(self.automaton)} patterns")

    def _check_word_boundary(self, text: str, start: int, end: int) -> bool:
        """Check if the match at position has proper word boundaries."""
        # Check left boundary
        if start > 0 and self.word_boundary_pattern.match(text[start - 1]):
            return False

        # Check right boundary
        if end < len(text) and self.word_boundary_pattern.match(text[end]):
            return False

        return True

    def find_violations(self, text: str) -> List[Dict]:
        violations = []
        seen_violations = set()  # Track (keyword, position) to avoid duplicates

        # Normalize text
        text_normalized = text.lower().replace("\u2011", "-")

        # Use Aho-Corasick to find all matches
        for end_pos, (keyword, data, match_type) in self.automaton.iter(
            text_normalized
        ):
            start_pos = end_pos - len(keyword) + 1

            # For single words, verify word boundaries
            if match_type == "word":
                if not self._check_word_boundary(
                    text_normalized, start_pos, end_pos + 1
                ):
                    continue

            # Avoid duplicate violations at the same position
            violation_key = (keyword, start_pos)
            if violation_key not in seen_violations:
                seen_violations.add(violation_key)
                violations.append(
                    {
                        "keyword": keyword,
                        "categories": data["categories"],
                        "severity": data["severity"],
                    }
                )

        return violations


class TranscriptParser:
    @staticmethod
    def parse_vtt(content: str) -> List[Utterance]:
        utterances = []
        blocks = content.strip().split("\n\n")

        for block in blocks:
            lines = block.strip().split("\n")
            if len(lines) < 3 or "WEBVTT" in lines[0]:
                continue

            # Parse timestamp line
            timestamp_match = re.search(
                r"(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})", block
            )
            if not timestamp_match:
                continue

            start_time = timestamp_match.group(1)
            end_time = timestamp_match.group(2)

            # Parse speaker and text
            for line in lines[2:]:
                if ":" in line:
                    parts = line.split(":", 1)
                    speaker = parts[0].strip()
                    text = parts[1].strip() if len(parts) > 1 else ""

                    if text:
                        utterances.append(
                            Utterance(speaker, text, start_time, end_time)
                        )

        return utterances


class ModerationEngine:
    def __init__(self, keywords_path: str):
        self.matcher = KeywordMatcher(self._load_keywords(keywords_path))

    def _load_keywords(self, csv_path: str) -> List[Dict]:
        keyword_data = []
        print(f"Loading keywords from {csv_path}...")
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if "cleaned_words" in row and row["cleaned_words"]:
                    # Parse categories from string representation of list
                    categories_str = row.get("mod_categories", "[]")
                    try:
                        # Handle string representation of list
                        import ast

                        categories = (
                            ast.literal_eval(categories_str) if categories_str else []
                        )
                    except (ValueError, SyntaxError):
                        categories = []

                    keyword_data.append(
                        {
                            "keyword": row["cleaned_words"],
                            "categories": categories,
                            "severity": row.get("mod_critical", "LOW"),
                        }
                    )
        print(f"Loaded {len(keyword_data)} keywords from CSV")
        return keyword_data

    def process_transcript(self, vtt_path: str) -> Dict:
        with open(vtt_path, "r", encoding="utf-8") as f:
            content = f.read()

        utterances = TranscriptParser.parse_vtt(content)
        violations = []

        for utterance in utterances:
            found_violations = self.matcher.find_violations(utterance.text)
            for violation_data in found_violations:
                violations.append(
                    Violation(
                        keyword=violation_data["keyword"],
                        speaker=utterance.speaker,
                        text=utterance.text,
                        timestamp=utterance.start_time,
                        categories=violation_data["categories"],
                        severity=violation_data["severity"],
                    )
                )

        # Calculate severity scores
        severity_scores = {"LOW": 1, "MEDIUM": 5, "HIGH": 10}
        compound_score = sum(severity_scores.get(v.severity, 1) for v in violations)

        # Find highest severity
        if violations:
            severity_order = ["HIGH", "MEDIUM", "LOW"]
            highest_severity = next(
                (
                    sev
                    for sev in severity_order
                    if any(v.severity == sev for v in violations)
                ),
                "LOW",
            )
        else:
            highest_severity = None

        # Create category-based report
        category_report = {}
        for violation in violations:
            for category in violation.categories:
                if category not in category_report:
                    category_report[category] = {
                        "count": 0,
                        "flags": [],
                        "speakers": set(),
                    }
                category_report[category]["count"] += 1
                category_report[category]["flags"].append(
                    {
                        "keyword": violation.keyword,
                        "speaker": violation.speaker,
                        "timestamp": violation.timestamp,
                        "severity": violation.severity,
                    }
                )
                category_report[category]["speakers"].add(violation.speaker)

        # Convert sets to lists for JSON serialization
        for category in category_report:
            category_report[category]["speakers"] = list(
                category_report[category]["speakers"]
            )

        return {
            "total_utterances": len(utterances),
            "total_flags": len(violations),
            "compound_severity_score": compound_score,
            "highest_severity_level": highest_severity,
            "flags": [asdict(v) for v in violations],
            "speakers_with_flags": list(set(v.speaker for v in violations)),
            "category_report": category_report,
        }


def moderate_transcript(
    transcript_path: str, keywords_csv_path: str, output_path: str = None
) -> Dict:
    """
    Main function to moderate a transcript against bad keywords.

    Args:
        transcript_path: Path to the .vtt transcript file
        keywords_csv_path: Path to the CSV file with bad keywords
        output_path: Optional path to save JSON output (defaults to transcript_moderation_results.json)

    Returns:
        Dictionary containing moderation results
    """
    engine = ModerationEngine(keywords_csv_path)
    results = engine.process_transcript(transcript_path)

    # Save to JSON file
    if output_path is None:
        output_path = "transcript_moderation_results.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"Results saved to {output_path}")

    return results


if __name__ == "__main__":
    # Example usage
    results = moderate_transcript(
        transcript_path="fake_transcript.vtt",
        keywords_csv_path="bad_keywords.csv",
        output_path="moderation_results_optimized.json",
    )

    print(f"Total flags found: {results['total_violations']}")
    for violation in results["flags"]:
        print(
            f"[{violation['timestamp']}] {violation['speaker']}: '{violation['keyword']}' in \"{violation['text']}\""
        )
