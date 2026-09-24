"use client";

import { createChart, CandlestickSeries, HistogramSeries, ColorType } from "lightweight-charts";
import type { IChartApi, UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef } from "react";
import type { MarketPrice } from "@/types";

/** OHLC が揃っている観測だけをローソク足にできる。欠損はゼロ補完せず除外する。 */
function toCandles(prices: MarketPrice[]) {
  return prices
    .filter((p) => p.open_price != null && p.high_price != null && p.low_price != null && p.close_price != null)
    .map((p) => ({
      time: (Date.parse(`${p.obs_date}T00:00:00Z`) / 1000) as UTCTimestamp,
      open: p.open_price as number,
      high: p.high_price as number,
      low: p.low_price as number,
      close: p.close_price as number,
    }));
}

function toVolumes(prices: MarketPrice[]) {
  return prices
    .filter((p) => p.volume != null)
    .map((p) => ({
      time: (Date.parse(`${p.obs_date}T00:00:00Z`) / 1000) as UTCTimestamp,
      value: p.volume as number,
      color: (p.close_price ?? 0) >= (p.open_price ?? 0) ? "#9cccae" : "#e0a3a3",
    }));
}

export default function PriceChart({ prices }: { prices: MarketPrice[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      layout: { background: { type: ColorType.Solid, color: "#ffffff" }, textColor: "#374151" },
      grid: { vertLines: { color: "#f3f4f6" }, horzLines: { color: "#f3f4f6" } },
      rightPriceScale: { borderColor: "#e5e7eb", scaleMargins: { top: 0.1, bottom: 0.3 } },
      timeScale: { borderColor: "#e5e7eb", timeVisible: false },
      height: 360,
      autoSize: true,
    });
    chartRef.current = chart;

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: "#2e7d52", downColor: "#c0392b",
      borderUpColor: "#2e7d52", borderDownColor: "#c0392b",
      wickUpColor: "#2e7d52", wickDownColor: "#c0392b",
    });
    candles.setData(toCandles(prices));

    const volumes = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    // 出来高は下部3割に重ねる。価格軸とは別スケールにする。
    chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.75, bottom: 0 } });
    volumes.setData(toVolumes(prices));

    chart.timeScale().fitContent();

    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [prices]);

  if (prices.length === 0) {
    return <p className="text-gray-500 text-sm py-12 text-center">価格データがありません</p>;
  }
  return <div ref={containerRef} className="w-full" />;
}
