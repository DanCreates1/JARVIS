import pyttsx3
import ollama
from ollama import ChatResponse

engine = pyttsx3.init()
engine.setProperty('volume', 0.5)

voices = engine.getProperty('voices')
engine.setProperty('voice', voices[1].id)

while True:
    user = input("Jarvis: ")

    response: ChatResponse = ollama.chat(
        model='llama2:text',
        messages=[
            {
                'role': 'system',
                'content': 'You are JARVIS, a real-time AI assistant; never narrate, never explain limitations, never roleplay dialogue, respond only as an active assistant, be concise and confident, ask for required input, and proceed with tasks immediately.'
            },
            {
                'role': 'user',
                'content': user
            }
        ]
    )

    reply = response.message.content.strip()
    print(reply)
    engine.say(reply)
    engine.runAndWait()
