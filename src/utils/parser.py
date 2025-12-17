"""Utility functions for parsing job data from markdown."""

import re
from typing import Optional


def extract_salary(text: str) -> Optional[str]:
    """Extract salary range from text.

    Handles formats like:
    - 20k-35k
    - 20K-35K
    - 20-35K
    - 2万-3.5万
    - 20000-35000

    Args:
        text: Text containing salary information

    Returns:
        Normalized salary string (e.g., "20k-35k") or None
    """
    if not text:
        return None

    # Pattern for Chinese format (万 = 10k)
    chinese_pattern = r"(\d+(?:\.\d+)?)\s*[万w]\s*[-~至到]\s*(\d+(?:\.\d+)?)\s*[万w]?"
    match = re.search(chinese_pattern, text, re.IGNORECASE)
    if match:
        low = float(match.group(1)) * 10
        high = float(match.group(2)) * 10
        return f"{int(low)}k-{int(high)}k"

    # Pattern for k format
    k_pattern = r"(\d+(?:\.\d+)?)\s*[kK]\s*[-~至到]\s*(\d+(?:\.\d+)?)\s*[kK]?"
    match = re.search(k_pattern, text)
    if match:
        low = match.group(1)
        high = match.group(2)
        return f"{low}k-{high}k"

    # Pattern for plain numbers (assumed to be monthly in yuan)
    number_pattern = r"(\d{4,6})\s*[-~至到]\s*(\d{4,6})"
    match = re.search(number_pattern, text)
    if match:
        low = int(match.group(1)) // 1000
        high = int(match.group(2)) // 1000
        return f"{low}k-{high}k"

    return None


def extract_experience(text: str) -> Optional[str]:
    """Extract experience requirement from text.

    Handles formats like:
    - 3-5年经验
    - 3年以上
    - 经验不限
    - 1-3 years

    Args:
        text: Text containing experience information

    Returns:
        Normalized experience string or None
    """
    if not text:
        return None

    # Check for "no requirement" patterns
    no_req_patterns = ["经验不限", "不限经验", "无经验要求", "no experience", "entry level"]
    for pattern in no_req_patterns:
        if pattern.lower() in text.lower():
            return "Entry Level"

    # Pattern for Chinese format
    chinese_pattern = r"(\d+)\s*[-~至到]\s*(\d+)\s*年"
    match = re.search(chinese_pattern, text)
    if match:
        return f"{match.group(1)}-{match.group(2)} years"

    # Pattern for "X年以上" (X+ years)
    plus_pattern = r"(\d+)\s*年以上"
    match = re.search(plus_pattern, text)
    if match:
        return f"{match.group(1)}+ years"

    # Pattern for English format
    english_pattern = r"(\d+)\s*[-~to]\s*(\d+)\s*years?"
    match = re.search(english_pattern, text, re.IGNORECASE)
    if match:
        return f"{match.group(1)}-{match.group(2)} years"

    return None


def normalize_location(text: str) -> str:
    """Normalize location string.

    Args:
        text: Raw location text

    Returns:
        Normalized location string
    """
    if not text:
        return "Beijing"

    # Common Beijing district names
    districts = {
        "海淀": "Haidian",
        "朝阳": "Chaoyang",
        "西城": "Xicheng",
        "东城": "Dongcheng",
        "丰台": "Fengtai",
        "石景山": "Shijingshan",
        "大兴": "Daxing",
        "通州": "Tongzhou",
        "昌平": "Changping",
        "顺义": "Shunyi",
    }

    text_lower = text.lower()

    # Check if it's Beijing
    if "北京" in text or "beijing" in text_lower:
        # Try to extract district
        for cn, en in districts.items():
            if cn in text:
                return f"Beijing, {en}"
        return "Beijing"

    return text.strip()


def extract_tags(text: str) -> list[str]:
    """Extract technology/skill tags from text.

    Args:
        text: Text containing skill mentions

    Returns:
        List of extracted tags
    """
    if not text:
        return []

    # Common tech keywords to look for
    tech_keywords = [
        "Python",
        "Java",
        "JavaScript",
        "TypeScript",
        "Go",
        "Golang",
        "Rust",
        "C++",
        "C#",
        "Ruby",
        "PHP",
        "Swift",
        "Kotlin",
        "React",
        "Vue",
        "Angular",
        "Node.js",
        "Django",
        "Flask",
        "FastAPI",
        "Spring",
        "SpringBoot",
        "Docker",
        "Kubernetes",
        "K8s",
        "AWS",
        "Azure",
        "GCP",
        "MySQL",
        "PostgreSQL",
        "MongoDB",
        "Redis",
        "Elasticsearch",
        "Kafka",
        "RabbitMQ",
        "Linux",
        "Git",
        "CI/CD",
        "DevOps",
        "Microservices",
        "REST",
        "GraphQL",
        "gRPC",
        "Machine Learning",
        "ML",
        "AI",
        "Deep Learning",
        "TensorFlow",
        "PyTorch",
        "NLP",
        "Computer Vision",
    ]

    found_tags = []
    text_lower = text.lower()

    for tag in tech_keywords:
        # Case-insensitive search but preserve original casing
        if tag.lower() in text_lower:
            # Normalize some tags
            normalized = tag
            if tag.lower() == "golang":
                normalized = "Go"
            elif tag.lower() == "k8s":
                normalized = "Kubernetes"
            elif tag.lower() == "springboot":
                normalized = "Spring Boot"

            if normalized not in found_tags:
                found_tags.append(normalized)

    return found_tags


def parse_salary_min(salary_range: Optional[str]) -> Optional[int]:
    """Parse the minimum salary from a salary range string.

    Args:
        salary_range: Salary string like "20k-35k", "15k-25k", etc.

    Returns:
        Minimum salary as integer (in k), or None if parsing fails
    """
    if not salary_range:
        return None

    # Match patterns like "20k-35k", "20K-35K", "20-35k"
    match = re.search(r"(\d+(?:\.\d+)?)\s*[kK]?\s*[-~至到]", salary_range)
    if match:
        return int(float(match.group(1)))

    # Try just a number at the start
    match = re.search(r"^(\d+(?:\.\d+)?)", salary_range)
    if match:
        return int(float(match.group(1)))

    return None


def parse_experience_years(exp_str: Optional[str]) -> Optional[tuple[int, int | None]]:
    """Parse experience string into (min, max) years.

    Args:
        exp_str: Experience string like "3-5 years", "5+ years", "Entry Level"

    Returns:
        Tuple of (min_years, max_years) or None. max_years can be None for "5+" format.
    """
    if not exp_str:
        return None

    # "Entry Level" or similar
    if "entry" in exp_str.lower() or exp_str == "0":
        return (0, 0)

    # Pattern for "3-5 years" format
    match = re.search(r"(\d+)\s*[-~to]\s*(\d+)", exp_str)
    if match:
        return (int(match.group(1)), int(match.group(2)))

    # Pattern for "5+ years" or "5年以上"
    match = re.search(r"(\d+)\s*\+", exp_str)
    if match:
        return (int(match.group(1)), None)

    # Just a number
    match = re.search(r"(\d+)", exp_str)
    if match:
        return (int(match.group(1)), int(match.group(1)))

    return None


def clean_text(text: str) -> str:
    """Clean and normalize text content.

    Args:
        text: Raw text

    Returns:
        Cleaned text
    """
    if not text:
        return ""

    # Remove excessive whitespace
    text = re.sub(r"\s+", " ", text)

    # Remove common markdown artifacts
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # [text](url) -> text
    text = re.sub(r"[*_]{1,2}([^*_]+)[*_]{1,2}", r"\1", text)  # **text** -> text

    return text.strip()
