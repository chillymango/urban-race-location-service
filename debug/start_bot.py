import requests

from src.server import StartBotRequest
from src.process.run_bot import BotProfile


if __name__ == "__main__":
    request = StartBotRequest(
        region="sf_north_beach",
        bot_type=BotProfile.RAMBLE,
        latitude=37.796731611152836,
        longitude=-122.39432425057922,
    )
    res = requests.post('http://localhost:8080/start', json=request.dict())
