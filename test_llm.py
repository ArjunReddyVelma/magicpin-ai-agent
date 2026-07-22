from services.llm_service import LLMService

llm = LLMService()

response = llm.generate(
    [
        {
            "role": "user",
            "content": "Say hello in one short sentence.",
        }
    ]
)

print(response)