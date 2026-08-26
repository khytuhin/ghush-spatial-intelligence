/* Loaded after MapLibre and before app.js. Keep the national overview less tightly cropped. */
(() => {
  if (!window.maplibregl?.Map?.prototype?.fitBounds) return;
  const original = window.maplibregl.Map.prototype.fitBounds;
  window.maplibregl.Map.prototype.fitBounds = function(bounds, options = {}, eventData) {
    try {
      const west = Number(bounds?.[0]?.[0]);
      const south = Number(bounds?.[0]?.[1]);
      const east = Number(bounds?.[1]?.[0]);
      const north = Number(bounds?.[1]?.[1]);
      const nationalExtent = [west, south, east, north].every(Number.isFinite) && (east - west) > 4.5 && (north - south) > 3.5;
      if (nationalExtent && options?.duration === 0) {
        options = {
          ...options,
          padding: { top: 92, right: 118, bottom: 92, left: 118 },
          maxZoom: Math.min(Number.isFinite(options.maxZoom) ? options.maxZoom : 9, 5.15)
        };
      }
    } catch {
      // Fall back to MapLibre's original behavior.
    }
    return original.call(this, bounds, options, eventData);
  };
})();
