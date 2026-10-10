import { HttpClient } from './http-client';
import type {
  InstallTrackRequest,
  InstalledTrackInfo,
  InstalledTracksResponse,
  MarketplaceResponse,
  RefreshTrackResponse,
  TrackActionResponse,
  TracksRequest,
  TracksResponse,
  SyncResponse,
  ToggleTrackResponse,
} from '../models/api';

export interface TracksClientOptions {
  host: string;
  apiKey?: string;
  timeout?: number;
}

export class TracksClient {
  public readonly host: string;
  public readonly apiKey?: string;
  private readonly client: HttpClient;

  constructor(options: TracksClientOptions) {
    this.host = options.host.replace(/\/$/, '');
    this.apiKey = options.apiKey;
    this.client = new HttpClient({
      baseUrl: this.host,
      apiKey: this.apiKey,
      timeout: options.timeout || 60000,
    });
  }

  async getTracks(request: TracksRequest = {}): Promise<TracksResponse> {
    const response = await this.client.post<TracksResponse>('/api/tracks', request);
    return response.data;
  }

  async syncTracks(): Promise<SyncResponse> {
    const response = await this.client.post<SyncResponse>('/api/tracks/sync', {});
    return response.data;
  }

  async installTrack(request: InstallTrackRequest): Promise<InstalledTrackInfo> {
    const response = await this.client.post<InstalledTrackInfo>('/api/tracks/install', request);
    return response.data;
  }

  async listInstalledTracks(): Promise<InstalledTracksResponse> {
    const response = await this.client.get<InstalledTracksResponse>('/api/tracks/installed');
    return response.data;
  }

  async getInstalledTrack(trackName: string): Promise<InstalledTrackInfo> {
    const response = await this.client.get<InstalledTrackInfo>(
      `/api/tracks/installed/${encodeURIComponent(trackName)}`
    );
    return response.data;
  }

  async toggleTrack(trackName: string, enabled: boolean): Promise<ToggleTrackResponse> {
    const response = await this.client.patch<ToggleTrackResponse>(
      `/api/tracks/installed/${encodeURIComponent(trackName)}`,
      { enabled }
    );
    return response.data;
  }

  async uninstallTrack(trackName: string): Promise<TrackActionResponse> {
    const response = await this.client.delete<TrackActionResponse>(
      `/api/tracks/installed/${encodeURIComponent(trackName)}`
    );
    return response.data;
  }

  async refreshTrack(trackName: string): Promise<RefreshTrackResponse> {
    const response = await this.client.post<RefreshTrackResponse>(
      `/api/tracks/installed/${encodeURIComponent(trackName)}/refresh`
    );
    return response.data;
  }

  async getMarketplace(): Promise<MarketplaceResponse> {
    const response = await this.client.get<MarketplaceResponse>('/api/tracks/marketplace');
    return response.data;
  }

  close(): void {
    this.client.close();
  }
}
