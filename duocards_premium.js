// ==UserScript==
// @name         DuoCards Premium Unlock (Visual & Functional)
// @namespace    http://tampermonkey.net/
// @version      1.1
// @description  Intercepts user profile data to inject a simulated premium subscription.
// @author       You
// @match        *://*.duocards.com/*
// @match        *://duocards.com/*
// @run-at       document-start
// @grant        none
// ==/UserScript==

(function () {
    'use strict';

    // Helper: The fake subscription object we want to inject
    const mockSubscription = {
        "transactionId": "simulated_premium_userscript",
        "timeToExpire": 4102444800000, // Date: Jan 01 2100
        "platform": "web",
        "storeId": "duocards_premium_yearly", // Required by schema
        "family": null // Required by schema (Scalar field, null is usually safe)
    };

    console.log("[DuoCards Unlock] Script loaded. Waiting for network requests...");

    // 1. Hook into window.fetch (Used by most modern GraphQL apps)
    const originalFetch = window.fetch;
    window.fetch = async function (...args) {
        const response = await originalFetch(...args);

        // We only care about successful JSON responses
        if (response.ok) {
            const clone = response.clone();
            try {
                const body = await clone.json();

                // Check if this response contains the "viewer" (User Profile)
                if (body && body.data && body.data.viewer) {
                    console.log("[DuoCards Unlock] Intercepted 'viewer' data. Injecting Premium...");
                    console.log(body.data);

                    // INJECT: Set the subscription
                    body.data.viewer.subscriptions = [mockSubscription];

                    // OPTIONAL: Hide "Kick" dialogs if they exist in the data
                    body.data.viewer.showSubsKickDialog = false;

                    // Return the modified response to the app
                    return new Response(JSON.stringify(body), {
                        status: response.status,
                        statusText: response.statusText,
                        headers: response.headers
                    });
                }
            } catch (err) {
                // If it's not JSON or fails to parse, just ignore it
                console.log("Error injecting");
            }
        }
        return response;
    };

})();