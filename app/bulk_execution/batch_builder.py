from typing import List


def split_into_batches(items: list, batch_size: int = 100) -> List[list]:
    return [
        items[index:index + batch_size]
        for index in range(0, len(items), batch_size)
    ]
