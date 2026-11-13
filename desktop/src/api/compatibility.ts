/**
 * Desktop Agent Release Engineering - Version & Compatibility Management (Phase 15)
 * Verifies runtime agent compatibility against backend policy and manages
 * update channel routing (staging vs. production).
 */

export interface CompatibilityStatus {
  isCompatible: boolean;
  currentAgentVersion: string;
  minimumBackendRequired: string;
  currentChannel: 'staging' | 'production';
  actionRequired: 'NONE' | 'RECOMMENDED_UPDATE' | 'MANDATORY_UPDATE' | 'UNSUPPORTED_OS';
  message: string;
}

export class VersionManager {
  public static readonly CURRENT_VERSION = '0.1.0';

  /**
   * Parse semantic version string (e.g., '0.1.0') into numeric components.
   */
  public static parseSemver(v: string): [number, number, number] {
    const clean = v.replace(/^v/, '').split('-')[0];
    const parts = clean.split('.').map((p) => parseInt(p, 10) || 0);
    return [parts[0] || 0, parts[1] || 0, parts[2] || 0];
  }

  /**
   * Compare two semver strings:
   * Returns > 0 if v1 > v2, 0 if v1 === v2, < 0 if v1 < v2.
   */
  public static compareSemver(v1: string, v2: string): number {
    const [maj1, min1, pat1] = this.parseSemver(v1);
    const [maj2, min2, pat2] = this.parseSemver(v2);

    if (maj1 !== maj2) return maj1 - maj2;
    if (min1 !== min2) return min1 - min2;
    return pat1 - pat2;
  }

  /**
   * Validate agent compatibility against backend minimum requirements.
   */
  public static checkCompatibility(
    backendMinVersion: string,
    currentVersion: string = this.CURRENT_VERSION,
    channel: 'staging' | 'production' = 'production'
  ): CompatibilityStatus {
    const cmp = this.compareSemver(currentVersion, backendMinVersion);

    if (cmp < 0) {
      return {
        isCompatible: false,
        currentAgentVersion: currentVersion,
        minimumBackendRequired: backendMinVersion,
        currentChannel: channel,
        actionRequired: 'MANDATORY_UPDATE',
        message: `Agent version ${currentVersion} is deprecated. Minimum required version is ${backendMinVersion}. Please update to continue recording attendance.`,
      };
    }

    return {
      isCompatible: true,
      currentAgentVersion: currentVersion,
      minimumBackendRequired: backendMinVersion,
      currentChannel: channel,
      actionRequired: 'NONE',
      message: `Agent version ${currentVersion} is fully compatible with platform services on channel [${channel.toUpperCase()}].`,
    };
  }
}

