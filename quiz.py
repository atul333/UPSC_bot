import os
import asyncio
import logging
import json
import hashlib
from datetime import datetime
from telegram import Bot, Poll
from telegram.error import TelegramError
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants from environment variables
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY not found in environment variables. Please set it in the .env file.")
    exit(1)
CHANNEL_ID = os.getenv('CHANNEL_ID')

if not TELEGRAM_TOKEN:
    logger.error("TELEGRAM_TOKEN not found in environment variables. Please set it in the .env file.")
    exit(1)

if not CHANNEL_ID:
    logger.error("CHANNEL_ID not found in environment variables. Please set it in the .env file.")
    exit(1)

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# Path to store asked questions
QUESTIONS_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'asked_questions.json')

# Initialize or load the questions database
def load_questions_db():
    if os.path.exists(QUESTIONS_DB_PATH):
        try:
            with open(QUESTIONS_DB_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.error("Error decoding questions database, creating new one")
            return {"questions": []}
    else:
        return {"questions": []}

# Save questions to database
def save_question_to_db(question):
    db = load_questions_db()
    
    # Create a hash of the question to use as a unique identifier
    question_hash = hashlib.md5(question.encode('utf-8')).hexdigest()
    
    # Check if this question (or very similar) has been asked before
    for q in db["questions"]:
        if q["hash"] == question_hash:
            logger.info("Question has been asked before, not saving")
            return False
    
    # Add the new question
    db["questions"].append({
        "hash": question_hash,
        "question": question,
        "date_added": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    
    # Save the updated database
    with open(QUESTIONS_DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Added new question to database. Total questions: {len(db['questions'])}")
    return True

async def generate_quiz_question():
    try:
        # Load previously asked questions to provide as context
        db = load_questions_db()
        
        # Get the number of previously asked questions
        num_previous_questions = len(db["questions"])
        
        # Create a context message with information about previously asked questions
        context_message = {
            "role": "system",
            "content": f"You have previously generated {num_previous_questions} questions. Ensure you create a completely new and unique question that has not been asked before."
        }
        
        # Main instruction message
        instruction_message = {
            "role": "system",
            "content": "Generate a challenging multiple choice question for UPSC/SSC CGL exam preparation. Follow this EXACT format and example:\n\nExample Output:\nWho was the first President of India?\nभारत के प्रथम राष्ट्रपति कौन थे?\n\nA) Dr. Rajendra Prasad / डॉ राजेंद्र प्रसाद\nB) Jawaharlal Nehru / जवाहरलाल नेहरू\nC) Sardar Vallabhbhai Patel / सरदार वल्लभभाई पटेल\nD) Dr. A.P.J. Abdul Kalam / डॉ ए पी जे अब्दुल कलाम\n\nCorrect: A\n\nRequirements:\n1. Generate ONLY tough, high-difficulty questions that require deep understanding of the subject\n2. Take reference from standard UPSC and SSC CGL preparation books and past exam papers\n3. NEVER repeat questions that are commonly asked; create unique questions that test advanced concepts\n4. Use high-level question-forming techniques with complex distractors that require critical thinking\n5. Cover ALL subjects relevant to UPSC/SSC CGL: Indian History, Geography, Polity, Economics, Science, Current Affairs, Reasoning, Quantitative Aptitude, English, etc.\n6. Question MUST be shown in both English and Hindi with accurate translations\n7. Hindi translation must be grammatically correct\n8. Each option MUST have both English and Hindi versions separated by ' / '\n9. Options MUST start with A), B), C), D) followed by a space\n10. Use proper Hindi Unicode characters\n11. Keep formatting consistent throughout"
        }
        
        # Add recent questions as examples of what not to repeat (if available)
        recent_questions = []
        if num_previous_questions > 0:
            # Get the 5 most recent questions or all if less than 5
            recent_count = min(5, num_previous_questions)
            recent_questions = db["questions"][-recent_count:]
            
        avoid_message = None
        if recent_questions:
            avoid_content = "DO NOT repeat these recently asked questions or anything too similar:\n\n"
            for i, q in enumerate(recent_questions):
                avoid_content += f"{i+1}. {q['question']}\n\n"
            
            avoid_message = {
                "role": "system",
                "content": avoid_content
            }
        
        # Construct the messages array
        messages = [context_message, instruction_message]
        if avoid_message:
            messages.append(avoid_message)
        
        response = client.chat.completions.create(
             model="gpt-3.5-turbo",
             messages=messages,
             temperature=0.7,
             max_tokens=400
         )
        
        question_text = response.choices[0].message.content.strip()
        
        # Parse the response with better error handling
        parts = question_text.split('\n\n')  # Split by double newlines to separate sections
        
        if len(parts) < 2:  # At least questions and options sections
            logger.error(f"Invalid response format. Got {len(parts)} sections, expected at least 2")
            logger.debug(f"Response content: {question_text}")
            return None, None, None
            
        # Extract questions (English and Hindi)
        question_lines = parts[0].strip().split('\n')
        if len(question_lines) != 2:
            logger.error(f"Invalid question format. Expected 2 lines, got {len(question_lines)}")
            return None, None, None
            
        question = '\n'.join(question_lines)
        
        # Extract and validate options
        options = []
        option_lines = parts[1].strip().split('\n')
        
        for line in option_lines:
            if any(line.startswith(f"{chr(ord('A') + i)}) ") for i in range(4)):
                option_text = line[3:].strip()  # Remove "X) " prefix
                if option_text and '/' in option_text:  # Ensure option has both languages
                    options.append(option_text)
        
        if len(options) != 4:
            logger.error(f"Invalid number of options: {len(options)}. Raw options: {option_lines}")
            return None, None, None
        
        # Extract and validate correct answer
        correct_line = parts[-1].strip() if len(parts) > 2 else option_lines[-1].strip()
        
        # Find the correct answer line
        for line in reversed(option_lines):
            if line.startswith("Correct:") or line.startswith("सही उत्तर:"):
                correct_line = line
                break
        
        # Extract correct answer letter, handling both English and Hindi formats
        if "Correct:" in correct_line:
            correct_answer = correct_line.split("Correct:", 1)[1].strip()
        elif "सही उत्तर:" in correct_line:
            correct_answer = correct_line.split("सही उत्तर:", 1)[1].strip()
        else:
            logger.error(f"Invalid correct answer format: {correct_line}")
            return None, None, None
            
        # Extract the letter from potential formats like "A) option / विकल्प"
        if "/" in correct_answer:
            correct_answer = correct_answer.split("/")[0].strip()
        if ")" in correct_answer:
            correct_answer = correct_answer.split(")")[0].strip()
            
        # Convert Hindi letters to English if needed
        hindi_to_eng = {'ए': 'A', 'बी': 'B', 'सी': 'C', 'डी': 'D'}
        if correct_answer in hindi_to_eng:
            correct_answer = hindi_to_eng[correct_answer]
            
        if correct_answer not in ['A', 'B', 'C', 'D']:
            logger.error(f"Invalid correct answer value: {correct_answer}")
            return None, None, None
            
        correct_index = ord(correct_answer) - ord('A')
        return question, options, correct_index
    except Exception as e:
        logger.error(f"Error generating question: {e}")
        return None, None, None

async def send_quiz(bot):
    try:
        logger.info("Generating new quiz question...")
        question, options, correct_index = await generate_quiz_question()
        
        if not all([question, options, correct_index is not None]):
            logger.error("Failed to generate valid quiz question, skipping this attempt")
            return
        
        # Save the question to our database to avoid repetition
        is_new = save_question_to_db(question)
        if not is_new:
            logger.warning("Generated question was too similar to a previous one, but proceeding anyway")
            
        logger.info(f"Sending quiz: {question[:50]}...")
        await bot.send_poll(
            chat_id=CHANNEL_ID,
            question=question,
            options=options,
            type=Poll.QUIZ,
            correct_option_id=correct_index,
            is_anonymous=True,
            explanation=f"Correct answer: {chr(correct_index + ord('A'))}"
        )
        logger.info("Quiz sent successfully")
        
    except TelegramError as e:
        logger.error(f"Telegram error while sending quiz: {e}")
        if 'Forbidden' in str(e):
            logger.error("Bot might not have proper permissions in the channel")
        elif 'Bad Request' in str(e):
            logger.error("Invalid quiz format or channel ID")
    except Exception as e:
        logger.error(f"Unexpected error while sending quiz: {e}", exc_info=True)

async def main():
    logger.info("Starting UPSC SSC CGL Quiz Bot...")
    try:
        bot = Bot(TELEGRAM_TOKEN)
        # Verify bot token by getting bot information
        bot_info = await bot.get_me()
        logger.info(f"Bot initialized successfully: @{bot_info.username}")
        
        retry_count = 0
        max_retries = 3
        
        while True:
            try:
                current_time = datetime.now()
                logger.info(f"Current time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
                
                await send_quiz(bot)
                # Reset retry count after successful quiz
                retry_count = 0
                
                # Wait for 1 hour before sending the next quiz
                logger.info("Waiting for 1 hour before sending next quiz...")
                await asyncio.sleep(3600)
                
            except Exception as e:
                retry_count += 1
                wait_time = min(60 * retry_count, 300)  # Max wait time of 5 minutes
                
                logger.error(f"Main loop error (attempt {retry_count}/{max_retries}): {e}", exc_info=True)
                
                if retry_count >= max_retries:
                    logger.error("Maximum retry attempts reached, resetting retry counter")
                    retry_count = 0
                
                logger.info(f"Waiting {wait_time} seconds before retrying...")
                await asyncio.sleep(wait_time)
                
    except Exception as e:
        logger.critical(f"Critical error in main loop: {e}", exc_info=True)
        raise

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        raise