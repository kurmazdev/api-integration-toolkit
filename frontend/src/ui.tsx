export const time = (date: string) =>
  new Date(date).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
export const date = (value: string) =>
  new Date(value).toLocaleDateString([], { month: "short", day: "numeric" });
export function Badge({ status }: { status: string }) {
  return (
    <span className={"badge " + status}>
      <i />
      {status.replace("_", " ")}
    </span>
  );
}
