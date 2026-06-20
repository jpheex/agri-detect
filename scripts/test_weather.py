import asyncio

from backend.agri_weather_ai import AgriWeatherAIEngine


async def main() -> None:
    engine = AgriWeatherAIEngine()
    report = await engine.evaluate_farm_health_risk("番茄", 23.9037, 120.6903)
    item = report.risk_assessments[0]
    print(item.disease_name, item.risk_level, item.risk_score)
    print("leaf_wetness_hours", report.current_weather.leaf_wetness_hours)


if __name__ == "__main__":
    asyncio.run(main())
