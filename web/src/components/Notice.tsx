type NoticeProps = {
  messages: string[];
  tone?: "error" | "info" | "success";
};

export function Notice({ messages, tone = "info" }: NoticeProps) {
  if (messages.length === 0) {
    return null;
  }
  return (
    <div className={`notice notice--${tone}`}>
      {messages.map((message) => (
        <div key={message}>{message}</div>
      ))}
    </div>
  );
}
