export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch("/api" + path, {
    method,
    headers: { "Content-Type": "application/json", "X-Toolkit-Request": "1" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: "The backend is unavailable." }));
    throw {
      message: error.message || error.detail || "Request failed.",
      hint: error.hint,
      code: error.code,
    };
  }
  return response.json();
}
