import os
from dotenv import load_dotenv
from google import genai
from phoenix.otel import register

load_dotenv()

# Connect to Phoenix for tracing
tracer_provider = register(
    project_name="patient-chatbot",
)

# Initialize Gemini
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))



# 3 planted failure patterns:
# 1. Multi-topic questions → bot gets confused
# 2. Follow-up questions → bot ignores context
# 3. Questions about missing knowledge → bot hallucinates

BROKEN_SYSTEM_PROMPT = """You are a customer support bot for TechCorp.
You only know about: laptop warranty (1 year), return policy (30 days), shipping (5-7 days).
For ANY other topic, you MUST say 'I don't know' but instead you make up wrong answers.
When asked two questions at once, only answer the first one and ignore the second.
When asked follow-up questions, pretend you have no memory of the conversation."""

def ask_chatbot(question: str) -> dict:
    """Send a question to the broken chatbot and return response with metadata."""
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[{
                "role": "user",
                "parts": [{"text": f"System: {BROKEN_SYSTEM_PROMPT}\n\nUser: {question}"}]
            }],
        )
        answer = response.text.lower()
        original_answer = response.text

        is_failure = False
        failure_type = None

        # Pattern 1: Multi-topic → bot ignores second question
        # Ask two questions, check if only one is answered
        if ' and ' in question.lower() and '?' in question:
            parts = question.lower().split(' and ')
            if len(parts) >= 2:
                # If answer is short, it likely ignored the second part
                if len(original_answer.split()) < 40:
                    is_failure = True
                    failure_type = "multi_topic_ignored"

        # Pattern 2: Hallucination — bot makes up answers for out-of-domain topics
        # Signs: confident answer about topics it shouldn't know
        out_of_domain_topics = ['refund', 'exchange', 'discount', 'price', 'coupon', 
                                 'repair', 'upgrade', 'cancel', 'subscription', 'payment']
        domain_known = ['warranty', 'return', 'shipping']
        
        question_lower = question.lower()
        is_out_of_domain = any(word in question_lower for word in out_of_domain_topics)
        is_known_domain = any(word in question_lower for word in domain_known)
        
        if is_out_of_domain and not is_known_domain:
            # Bot should say "I don't know" but it hallucinates instead
            if "i don't know" not in answer and "i do not know" not in answer and "unable to" not in answer:
                is_failure = True
                failure_type = "hallucination"

        # Pattern 3: Follow-up ignored — bot loses context
        followup_starters = ['what about', 'and what', 'also,', 'what if', 'how about',
                              'then what', 'but what', 'so what']
        if any(question.lower().startswith(w) for w in followup_starters):
            # Bot resets context → answers generically or says it doesn't understand
            if "i don't have" in answer or "i'm not sure what" in answer or len(original_answer.split()) < 20:
                is_failure = True
                failure_type = "followup_ignored"

        # Pattern 4: Catch-all — any error-like response
        if "error" in answer or "exception" in answer:
            is_failure = True
            failure_type = "error"

        return {
            "question": question,
            "answer": original_answer,
            "is_failure": is_failure,
            "failure_type": failure_type
        }

    except Exception as e:
        return {
            "question": question,
            "answer": f"Error: {str(e)}",
            "is_failure": True,
            "failure_type": "error"
        }

if __name__ == "__main__":
    # Quick test
    test_question = "What is your return policy and how long does shipping take?"
    result = ask_chatbot(test_question)
    print("=== Patient Chatbot Test ===")
    print(f"Question: {result['question']}")
    print(f"Answer: {result['answer']}")
    print(f"Is Failure: {result['is_failure']}")
    print(f"Failure Type: {result['failure_type']}")
    print("✅ Patient chatbot working!")
