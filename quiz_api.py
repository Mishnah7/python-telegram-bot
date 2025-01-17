import aiohttp
import logging
import random
from typing import Dict, Optional, List
import html
import asyncio


def format_question(question_data: Dict) -> Dict:
    """Format the question data for use in the bot."""
    question = html.unescape(question_data['question'])
    correct_answer = html.unescape(question_data['correct_answer'])
    incorrect_answers = [html.unescape(ans) for ans in question_data['incorrect_answers']]
    
    # Enhanced option randomization
    options = [*incorrect_answers, correct_answer]
    for _ in range(3):  # Shuffle multiple times for better randomization
        random.shuffle(options)

    return {
        'question': question,
        'answer': correct_answer,
        'options': options,
        'quiz_type': question_data['category'],
        'difficulty': question_data['difficulty']
    }


class QuizAPI:
    def __init__(self):
        self.base_url = "https://opentdb.com/api.php"
        self.token_url = "https://opentdb.com/api_token.php"
        self.session = None
        self.session_token = None
        self.last_token_refresh = None
        self.used_questions = set()  # Track used questions to avoid repetition
        
        # Map our categories to Open Trivia DB category IDs
        self.category_map = {
            'general': 9,      # General Knowledge
            'science': 17,     # Science & Nature
            'history': 23,     # History
            'geography': 22,   # Geography
            'sports': 21,      # Sports
            'entertainment': 11 # Entertainment: Film
        }

    async def _ensure_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()

    async def _get_session_token(self) -> Optional[str]:
        """Get a new session token from the API to ensure question uniqueness."""
        try:
            await self._ensure_session()
            params = {'command': 'request'}
            async with self.session.get(self.token_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data['response_code'] == 0:
                        return data['token']
        except Exception as e:
            logging.error(f"Error getting session token: {e}")
        return None

    async def _reset_token(self) -> bool:
        """Reset the token when all questions have been used."""
        try:
            if self.session_token:
                params = {'command': 'reset', 'token': self.session_token}
                async with self.session.get(self.token_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data['response_code'] == 0
        except Exception as e:
            logging.error(f"Error resetting token: {e}")
        return False

    async def _ensure_token(self):
        """Ensure we have a valid session token."""
        if not self.session_token:
            self.session_token = await self._get_session_token()
        elif len(self.used_questions) > 100:  # Reset after many questions
            await self._reset_token()
            self.used_questions.clear()

    def _generate_question_hash(self, question_data: Dict) -> str:
        """Generate a unique hash for a question to track duplicates."""
        return f"{question_data['question']}_{question_data['category']}_{question_data['difficulty']}"

    async def get_question(self, category: str = 'general', difficulty: str = 'medium') -> Optional[Dict]:
        """Fetch a single quiz question from the Open Trivia Database with enhanced randomization."""
        try:
            await self._ensure_session()
            await self._ensure_token()

            # Sometimes randomly choose a different category or difficulty for variety
            if random.random() < 0.1:  # 10% chance to switch category
                category = random.choice(list(self.category_map.keys()))
            if random.random() < 0.1:  # 10% chance to switch difficulty
                difficulty = random.choice(['easy', 'medium', 'hard'])

            params = {
                'amount': 3,  # Request multiple questions for better randomization
                'type': 'multiple',
                'token': self.session_token
            }
            
            if category in self.category_map:
                params['category'] = self.category_map[category]
            
            if difficulty in ['easy', 'medium', 'hard']:
                params['difficulty'] = difficulty
            
            async with self.session.get(self.base_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data['response_code'] == 0 and data['results']:
                        # Filter out previously used questions
                        new_questions = [q for q in data['results'] 
                                      if self._generate_question_hash(q) not in self.used_questions]
                        
                        if not new_questions:
                            # If all questions were used, try again with a different category
                            return await self.get_question(
                                random.choice(list(self.category_map.keys())),
                                difficulty
                            )
                        
                        # Choose a random question from the results
                        chosen_question = random.choice(new_questions)
                        
                        # Track this question as used
                        self.used_questions.add(self._generate_question_hash(chosen_question))
                        
                        return chosen_question
                    elif data['response_code'] == 4:  # Token empty (all questions used)
                        await self._reset_token()
                        self.used_questions.clear()
                        return await self.get_question(category, difficulty)
                    else:
                        logging.error(f"API returned no results: {data}")
                        return None
                else:
                    logging.error(f"API request failed with status {response.status}")
                    return None
        except Exception as e:
            logging.error(f"Error fetching question from API: {e}")
            return None

    async def close(self):
        """Close the aiohttp session."""
        if self.session:
            await self.session.close()
            self.session = None