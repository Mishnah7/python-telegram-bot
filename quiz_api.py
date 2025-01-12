import aiohttp
import logging
import random
from typing import Dict, Optional
import html


def format_question(question_data: Dict) -> Dict:
    """Format the question data for use in the bot."""
    question = html.unescape(question_data['question'])
    correct_answer = html.unescape(question_data['correct_answer'])
    incorrect_answers = [html.unescape(ans) for ans in question_data['incorrect_answers']]
    
    options = [*incorrect_answers, correct_answer]
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
        self.session = None

    async def _ensure_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()

    async def get_question(self) -> Optional[Dict]:
        """Fetch a single quiz question from the Open Trivia Database."""
        try:
            await self._ensure_session()
            params = {
                'amount': 1,
                'type': 'multiple'
            }
            
            async with self.session.get(self.base_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data['response_code'] == 0 and data['results']:
                        return data['results'][0]
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