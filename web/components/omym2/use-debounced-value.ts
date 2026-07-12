/*
Summary: Returns a value that trails its input by a fixed delay.
Why: Keeps keystroke-driven browse search from firing a request per keypress.
*/

"use client"

import { useEffect, useState } from "react"

export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [delayMs, value])
  return debounced
}
