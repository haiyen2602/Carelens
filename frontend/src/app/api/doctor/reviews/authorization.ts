// Cung mau voi app/api/accounts/authorization.ts.
export function forwardAuthorization(request: Request): Record<string, string> {
  const authorization = request.headers.get("authorization");
  return authorization ? { Authorization: authorization } : {};
}
