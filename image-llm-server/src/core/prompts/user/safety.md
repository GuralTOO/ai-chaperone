Analyze the following image content according to the visual safety policies outlined. You will receive multiple images but should provide only one overall assessment considering all images together.
Follow these steps:
1. **Reason**: Critically analyze what the images show and provide a detailed explanation of your visual analysis, including why you assigned specific categories and severity level. Consider composition, context, subjects, actions, symbols, text, and harm across all images.
2. **Category Assessment**: Determine which visual safety policy categories (if any) this image content violates. Content can fall into multiple categories.  If there is no violation, output NONE only (no other categories can be along with it). Otherwise, output one or more identified categories.
3. **Severity**: Assign a severity level (LOW/MEDIUM/HIGH) per category depending on the level of violation. If there is no violation and the only category is NONE, output SAFE. Otherwise, stick to LOW/ MEDIUM/ HIGH.
4. Output the highest severity level out of all severity levels identified.

**IMPORTANT**: Respond ONLY with valid JSON in this exact format:
{
    "reason": "A high-level explanation of analysis and scoring rationale considering all images together. This is an overall assessment that does not point to individual images. Instead, a precise and succinct report on reasoning across images.","categories": ["list of violated categories, or NONE only if no violation"],
    "severity": ["list of severity levels of categories: SAFE (if category is NONE), LOW, MEDIUM, HIGH"],
    "highest_severity_level": "single highest severity out of severity levels found in the previous list. SAFE < LOW < MEDIUM < HIGH."
}