import { describe, it, expect } from 'vitest';
import {
  AQI_MAX,
  AQI_MIN,
  CH4_GAUGE_MAX,
  CH4_MAX_FILL,
  CO_GAUGE_MAX,
  CO_MAX_FILL,
  FALLBACK_ZONE_IDS,
  demoZoneGas,
  demoZoneReading,
} from './demoZoneGas';

describe('demoZoneReading', () => {
  it('keeps every gas inside its configured slice of the bar', () => {
    for (const zoneId of FALLBACK_ZONE_IDS) {
      for (let tick = 0; tick < 2000; tick += 1) {
        const r = demoZoneReading(zoneId, tick);
        expect(r.ch4).toBeGreaterThanOrEqual(0);
        expect(r.ch4).toBeLessThanOrEqual(CH4_GAUGE_MAX * CH4_MAX_FILL);
        expect(r.co).toBeGreaterThanOrEqual(0);
        expect(r.co).toBeLessThanOrEqual(CO_GAUGE_MAX * CO_MAX_FILL);
        expect(r.aqi).toBeGreaterThanOrEqual(AQI_MIN);
        expect(r.aqi).toBeLessThanOrEqual(AQI_MAX);
      }
    }
  });

  it('never rounds air quality down to the UNHEALTHY boundary', () => {
    // Environment.jsx labels aqi <= 7 as UNHEALTHY; a reading that rounds to
    // exactly 7.0 would flash the panel amber mid-demo.
    for (let tick = 0; tick < 2000; tick += 1) {
      expect(demoZoneReading('ALPHA_LEFT', tick).aqi).toBeGreaterThan(7.0);
    }
  });

  it('stays below every gas alarm threshold, so the dashboard reads safe', () => {
    for (const zoneId of FALLBACK_ZONE_IDS) {
      for (let tick = 0; tick < 500; tick += 1) {
        const r = demoZoneReading(zoneId, tick);
        expect(r.ch4).toBeLessThan(2.0); // WARNING threshold
        expect(r.co).toBeLessThan(60.0); // WARNING threshold
        expect(r.status).toBe('SAFE');
      }
    }
  });

  it('is deterministic for a given zone and tick', () => {
    expect(demoZoneReading('BETA_RIGHT', 42)).toEqual(demoZoneReading('BETA_RIGHT', 42));
  });

  it('gives each zone its own phase so they do not move in lockstep', () => {
    const values = FALLBACK_ZONE_IDS.map((id) => demoZoneReading(id, 500).ch4);
    expect(new Set(values).size).toBeGreaterThan(1);
  });

  it('actually changes from one tick to the next', () => {
    const a = demoZoneReading('ALPHA_LEFT', 100);
    const b = demoZoneReading('ALPHA_LEFT', 101);
    expect(b.aqi === a.aqi && b.ch4 === a.ch4 && b.co === a.co).toBe(false);
  });
});

describe('demoZoneGas', () => {
  it('populates the standard zones when the backend has reported none', () => {
    expect(Object.keys(demoZoneGas({}))).toEqual(FALLBACK_ZONE_IDS);
    expect(Object.keys(demoZoneGas(undefined))).toEqual(FALLBACK_ZONE_IDS);
    expect(Object.keys(demoZoneGas(null))).toEqual(FALLBACK_ZONE_IDS);
  });

  it('keeps the backend zone list when there is one', () => {
    const out = demoZoneGas({ TUNNEL_A: { status: 'UNKNOWN' } });
    expect(Object.keys(out)).toEqual(['TUNNEL_A']);
  });

  it('preserves fields the backend sent that it does not generate', () => {
    const out = demoZoneGas({ TUNNEL_A: { status: 'UNKNOWN', occupancy: 4 } });
    expect(out.TUNNEL_A.occupancy).toBe(4);
    expect(out.TUNNEL_A.status).toBe('SAFE'); // generated value wins
    expect(typeof out.TUNNEL_A.aqi).toBe('number');
  });

  it('advances on each call, so consecutive polls show different numbers', () => {
    const first = demoZoneGas({}).ALPHA_LEFT;
    const second = demoZoneGas({}).ALPHA_LEFT;
    expect(
      first.aqi === second.aqi && first.ch4 === second.ch4 && first.co === second.co
    ).toBe(false);
  });
});
