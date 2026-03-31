from __future__ import annotations

import sys
from collections.abc import Iterable, Iterator
from typing import TypeVar

from tqdm.auto import tqdm


T = TypeVar("T")


def iter_progress(
    iterable: Iterable[T],
    *,
    total: int | None = None,
    desc: str,
    unit: str,
) -> Iterator[T]:
    return tqdm(
        iterable,
        total=total,
        desc=desc,
        unit=unit,
        dynamic_ncols=True,
        leave=False,
        disable=not sys.stderr.isatty(),
    )
