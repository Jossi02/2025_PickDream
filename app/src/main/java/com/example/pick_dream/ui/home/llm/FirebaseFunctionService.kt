package com.example.pick_dream.ui.home.llm

import android.os.Handler
import android.os.Looper
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

object FirebaseFunctionService {
    private val client = OkHttpClient.Builder()
        .connectTimeout(60, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .build()
    private val mainHandler = Handler(Looper.getMainLooper())


    private const val FUNCTION_URL =
        "https://ai-assistant-sicwnrweaa-uc.a.run.app"

    fun sendMessageToFunction(
        message: String,
        idToken: String,
        onSuccess: (String) -> Unit,
        onFailure: (Exception) -> Unit
    ) {
        val json = JSONObject().apply {
            put("message", message)
            put("supportsStructuredResponse", true)
        }
        val body = json.toString().toRequestBody("application/json".toMediaType())

        val request = Request.Builder()
            .url(FUNCTION_URL)
            .addHeader("Authorization", "Bearer $idToken")
            .post(body)
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                mainHandler.post {
                    onFailure(e)
                }
            }

            override fun onResponse(call: Call, response: Response) {
                response.use {
                    val result = it.body?.string()
                    if (result != null) {
                        mainHandler.post {
                            onSuccess(result)
                        }
                    } else {
                        mainHandler.post {
                            onFailure(IOException("응답이 없습니다."))
                        }
                    }
                }
            }
        })
    }
}
