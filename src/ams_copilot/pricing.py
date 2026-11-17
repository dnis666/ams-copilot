def cost_usd(
    price_table: dict[str, tuple[float, float]], model: str, prompt_tokens: int, completion_tokens: int
) -> float:
    prices = price_table.get(model)
    if prices is None:
        candidates = [key for key in price_table if model.startswith(key)]
        prices = price_table[max(candidates, key=len)] if candidates else (0.0, 0.0)
    input_price, output_price = prices
    return round((prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000, 6)
