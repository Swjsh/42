"use client";

interface Props {
  text: string;
}

export default function SpeechBubble({ text }: Props) {
  return (
    <div className="speech-bubble" role="note">
      {text}
    </div>
  );
}
