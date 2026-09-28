#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_event.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_eth.h"
#include "esp_eth_mac_openeth.h"
#include "esp_eth_phy.h"

static const char *TAG = "qemu_device";

static void on_eth_event(
    void *arg,
    esp_event_base_t event_base,
    int32_t event_id,
    void *event_data)
{
    switch (event_id) {
    case ETHERNET_EVENT_CONNECTED:
        ESP_LOGI(TAG, "Ethernet link up");
        break;

    case ETHERNET_EVENT_DISCONNECTED:
        ESP_LOGW(TAG, "Ethernet link down");
        break;

    case ETHERNET_EVENT_START:
        ESP_LOGI(TAG, "Ethernet started");
        break;

    case ETHERNET_EVENT_STOP:
        ESP_LOGI(TAG, "Ethernet stopped");
        break;

    default:
        break;
    }
}

static void on_ip_event(
    void *arg,
    esp_event_base_t event_base,
    int32_t event_id,
    void *event_data)
{
    if (event_id != IP_EVENT_ETH_GOT_IP) {
        return;
    }

    ip_event_got_ip_t *event = (ip_event_got_ip_t *)event_data;

    ESP_LOGI(
        TAG,
        "Got IP: " IPSTR,
        IP2STR(&event->ip_info.ip)
    );

    ESP_LOGI(
        TAG,
        "Gateway: " IPSTR,
        IP2STR(&event->ip_info.gw)
    );

    ESP_LOGI(
        TAG,
        "Netmask: " IPSTR,
        IP2STR(&event->ip_info.netmask)
    );
}

static void http_task(void *arg)
{
    /*
     * QEMU user-mode networking normally exposes the host as 10.0.2.2.
     *
     * Docker publishes the backend on the host's port 8080.
     */
    const char *url = "http://10.0.2.2:8080/health";

    esp_http_client_config_t config = {
        .url = url,
        .timeout_ms = 5000,
    };

    esp_http_client_handle_t client =
        esp_http_client_init(&config);

    if (client == NULL) {
        ESP_LOGE(TAG, "Failed to create HTTP client");
        vTaskDelete(NULL);
        return;
    }

    while (1) {
        ESP_LOGI(TAG, "GET %s", url);

        esp_err_t err = esp_http_client_perform(client);

        if (err == ESP_OK) {
            int status = esp_http_client_get_status_code(client);
            int length = esp_http_client_get_content_length(client);

            ESP_LOGI(
                TAG,
                "HTTP status=%d content_length=%d",
                status,
                length
            );
        } else {
            ESP_LOGE(
                TAG,
                "HTTP request failed: %s",
                esp_err_to_name(err)
            );
        }

        vTaskDelay(pdMS_TO_TICKS(5000));
    }

    esp_http_client_cleanup(client);
}

void app_main(void)
{
    ESP_LOGI(TAG, "Starting QEMU Ethernet device");

    ESP_ERROR_CHECK(esp_netif_init());

    ESP_ERROR_CHECK(
        esp_event_loop_create_default()
    );

    esp_netif_config_t netif_cfg =
        ESP_NETIF_DEFAULT_ETH();

    esp_netif_t *eth_netif =
        esp_netif_new(&netif_cfg);

    ESP_ERROR_CHECK(
        esp_event_handler_register(
            ETH_EVENT,
            ESP_EVENT_ANY_ID,
            &on_eth_event,
            NULL
        )
    );

    ESP_ERROR_CHECK(
        esp_event_handler_register(
            IP_EVENT,
            IP_EVENT_ETH_GOT_IP,
            &on_ip_event,
            NULL
        )
    );

    /*
     * OpenCores Ethernet MAC provided by QEMU.
     */
    eth_mac_config_t mac_config = ETH_MAC_DEFAULT_CONFIG();

    esp_eth_mac_t *mac =
        esp_eth_mac_new_openeth(&mac_config);

    if (mac == NULL) {
        ESP_LOGE(TAG, "Failed to create OpenCores Ethernet MAC");
        abort();
    }

    /*
     * QEMU's OpenCores MAC doesn't need a real external
     * LAN8720/DP83848 PHY.
     *
     * The OpenETH driver handles the emulated MAC directly.
     */
    eth_phy_config_t phy_config = ETH_PHY_DEFAULT_CONFIG();

    esp_eth_phy_t *phy =
        esp_eth_phy_new_generic(&phy_config);

    if (phy == NULL) {
        ESP_LOGE(TAG, "Failed to create generic Ethernet PHY");
        abort();
    }
    /* QEMU doesn't emulate PHY speed, so accept any value */
    esp_eth_config_t eth_config =
        ETH_DEFAULT_CONFIG(mac, phy);

    esp_eth_handle_t eth_handle = NULL;

    ESP_ERROR_CHECK(
        esp_eth_driver_install(
            &eth_config,
            &eth_handle
        )
    );

    ESP_ERROR_CHECK(
        esp_netif_attach(
            eth_netif,
            esp_eth_new_netif_glue(eth_handle)
        )
    );

    ESP_ERROR_CHECK(
        esp_eth_start(eth_handle)
    );

    ESP_LOGI(TAG, "Ethernet initialization complete");

    xTaskCreate(
        http_task,
        "http_task",
        4096,
        NULL,
        5,
        NULL
    );
}