"use client";

import TradingFloor from "./TradingFloor";

interface Props {
  data: any;
}

export default function Office({ data }: Props) {
  return (
    <div
      style={{
        width: "100%",
        aspectRatio: "2172 / 724",
        maxHeight: "100%",
        position: "relative",
        overflow: "hidden",
        borderRadius: 6,
      }}
    >
      <TradingFloor data={data} />
    </div>
  );
}
