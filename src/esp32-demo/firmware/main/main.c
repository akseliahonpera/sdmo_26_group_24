#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

void app_main(void)
{
    float temperature = 20.0;

    while (1) {
        printf("Temperature: %.1f C\n", temperature);

        temperature += 0.5;

        if (temperature > 30.0) {
            temperature = 20.0;
        }

        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
