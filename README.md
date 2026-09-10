# Traffic Oracle

Traffic Oracle periodically records travel times and taxi-price estimates for configured routes, then serves a provisioned Grafana dashboard.

Currently Snapp and Tapsi price collection is supported. Travel times are collected using Neshan API.

## Requirements

The app calls Snapp, Tapsi, and Neshan web services. Set the following values in `.env`:

- `NESHAN_API_KEY`: create an account at the [Neshan developer portal](https://platform.neshan.org/), enable the Distance Matrix service, and create an API key.
- `SNAPP_API_KEY`: sign in to the [Snapp passenger web app](https://app.snapp.taxi/), open your browser’s developer tools, and make a price request. In the request’s headers, find `Authorization: Bearer <token>` and copy only the value after `Bearer` into `SNAPP_API_KEY`.
- `SNAPP_API_REFRESH_TOKEN`: in the same devtools session, open Application/Storage → Local Storage for `app.snapp.taxi` and copy the `refreshToken` value. When `SNAPP_API_KEY` expires, `fetch-taxi.py` uses this to automatically obtain a new access token, and saves both new values to `token-state.json` (used from then on in place of the `.env` values, which stay as the initial seed).
- `TAPSI_API_KEY`: sign in to the [Tapsi passenger web app](https://app.tapsi.cab/), open your browser’s developer tools, and make a ride-preview request. In the request’s `Cookie` header, find `accessToken=<token>` and copy only that token value into `TAPSI_API_KEY`. This access token may expire and need refreshing; Tapsi's token currently has a long lifetime and no automatic refresh is implemented for it.

## Run

Create your local configuration from the supplied templates:

```sh
cp .env.example .env
cp origins.yaml.example origins.yaml
touch token-state.json
```

`token-state.json` holds refreshed Snapp tokens once auto-refresh kicks in; it must exist as a file before `docker compose up` since it's bind-mounted into the fetcher container.

Set the credentials and Grafana settings in `.env`, then define the route pairs in `origins.yaml`. `FETCH_INTERVAL_MINUTES` controls the scheduler interval.

Start the project:

```sh
docker compose up -d --build
```

Open the value of `GRAFANA_SERVER_ROOT_URL` in `.env` and sign in with `GRAFANA_ADMIN_USER` and `GRAFANA_ADMIN_PASSWORD`. The Traffic Oracle dashboard is the default landing page.

App logs can be accessed using `docker compose logs`.
