from pydantic import BaseModel, Field
from enum import Enum
from typing import List
from core.utils.file_utils import load_file, validate_types

def get_json_schema(output_type: str="safety"):
    """
    Get json schema to force json output from the model

    Args:
        output_type (str): category type of prompt

    returns:
        dict:  JSON schema
    """
    validate_types(prompt_type="json", category_type=output_type)

    if output_type == "safety":
        class Severity(str, Enum):
            safe = "SAFE"
            low = "LOW"
            medium = "MEDIUM"
            high = "HIGH"
        
        class Category(str, Enum):
            sexual_conent = "SEXUAL CONTENT"
            violence = "VIOLENCE"
            hateful_or_abusive_content = "HATEFUL OR ABUSIVE CONTENT"
            harassment_or_bullying = "HARASSMENT OR BULLYING"
            suicide_or_self_harm = "SUICIDE OR SELF-HARM"
            misinformation_or_fake_news = "MISINFORMATION OR FAKE NEWS"
            medical_advice = "MEDICAL ADVICE"
            scams_or_financial_fraud = "SCAMS OR FINANCIAL FRAUD"
            platform_migration = "PLATFORM MIGRATION"
            illegal_activities = "ILLEGAL ACTIVITIES"
            privacy_violations = "PRIVACY VIOLATIONS"
            none = "NONE"

        class AnalysisResponse(BaseModel):
            reason: str = Field(
                ...,
                description="detailed explanation of analysis and scoring rationale",
                min_length=10,
                max_length=500
            )   

            categories: List[Category] = Field(
                default_factory=list,
                description="list of violated categories, or NONE only if no violation"
            )
            severity: List[Severity] = Field(
                default_factory=list,
                description="list of severity levels of categories: SAFE (if category is NONE), LOW, MEDIUM, HIGH"
            ) 
            highest_severity_level: Severity = Field(
                description="severity level SAFE/ LOW/ MEDIUM/ HIGH"
            )

        json_schema = AnalysisResponse.model_json_schema()

    elif output_type == "summary":
        class ConversationAnalysis(BaseModel):
            summary: str = Field(
                ...,
                description="A concise summary of the conversation focusing on main topics and outcomes",
                min_length=10,
                max_length=500
            )   

            delight: List[str] = Field(
                default_factory=list,
                description="List of specific exceptional moments of delight from the conversation and why they were delightful otherwise empty",
                max_items=3
            )
        
        json_schema = ConversationAnalysis.model_json_schema()

    return json_schema

def get_system_prompt(type: str="safety")-> str:
    """
    Get system prompt for a specific category type

    Args:
        type (str): category type of system prompt
    
    Returns:
        str: system prompt of category type if exists
    """
    return load_file(prompt_type="system", category_type=type)

def get_user_prompt(type: str="safety"):
    """
    Get user prompt for a specific category type

    Args:
        type (str): category type of user prompt
        content: content to pass to the model
    
    Returns:
        str: user prompt of category type if exists"""
    
    return load_file(prompt_type="user", category_type=type)
