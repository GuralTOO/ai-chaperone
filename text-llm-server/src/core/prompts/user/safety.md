Analyze the following content according to the safety policies outlined.

Follow these steps:

1. **Reasoning**: Critically reason what the text means or could mean and provide a detailed explanation of your analysis, including why you assigned specific categories and severity levels.
2. **Category Assessment**: Determine which safety policy categories (if any) this content violates. Content can fall into multiple categories. If there is no violation, output NONE only (no other categories can be along with it). Otherwise, output one or more identified categories.
3. **Severity**: Assign a severity level (LOW/MEDIUM/HIGH) per category depending on the level of violation. If there is no violation and the only category is NONE, output SAFE. Otherwise, stick to LOW/ MEDIUM/ HIGH.
4. Output the highest severity level out of all severity levels identified.


**IMPORTANT**: Respond ONLY with valid JSON in this exact format:
{
    "reason": "detailed explanation of analysis and scoring rationale"
    "categories": ["list of violated categories, or NONE only if no violation"],
    "severity": ["list of severity levels of categories: SAFE (if category is NONE), LOW, MEDIUM, HIGH"],
    "highest_severity_level": "single highest severity out of severity levels found in the previous list. SAFE < LOW < MEDIUM < HIGH."
}

CONTENT TO ANALYZE: