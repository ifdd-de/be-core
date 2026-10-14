/*
 * Starts Swagger UI on /docs of an IFDD backend.
 *
 * Part of ifdd-be-core (BSD-3-Clause). The page that loads this file has no
 * inline script, so it works under a Content-Security-Policy with
 * script-src 'self'. Everything that differs per instance is read from the
 * data-* attributes of the element #swagger-ui, which the backend renders:
 *
 *   data-openapi-url          URL of the OpenAPI document, e.g. /openapi.json
 *   data-oauth2-redirect-url  path of the OAuth2 redirect page
 *   data-client-id            OIDC client for "Authorize" (empty: no login)
 *   data-scopes               scopes requested at login, space-separated
 *
 * The options match those FastAPI uses for its own /docs page, plus:
 *   persistAuthorization  keeps the login across page reloads (the token is
 *                         stored in the browser's localStorage of this host)
 *   validatorUrl: null    no request to the public swagger.io validator
 */
(function () {
  "use strict";

  var element = document.getElementById("swagger-ui");
  var data = element.dataset;

  var ui = SwaggerUIBundle({
    url: data.openapiUrl,
    dom_id: "#swagger-ui",
    layout: "BaseLayout",
    deepLinking: true,
    showExtensions: true,
    showCommonExtensions: true,
    persistAuthorization: true,
    validatorUrl: null,
    oauth2RedirectUrl: window.location.origin + data.oauth2RedirectUrl,
    presets: [
      SwaggerUIBundle.presets.apis,
      SwaggerUIBundle.SwaggerUIStandalonePreset
    ]
  });

  if (data.clientId) {
    // Authorization code flow with PKCE (S256) for a public client: no
    // client secret is sent or stored.
    ui.initOAuth({
      clientId: data.clientId,
      scopes: data.scopes,
      usePkceWithAuthorizationCodeGrant: true
    });
  }

  window.ui = ui;
})();
