package com.example.pick_dream.ui.home.llm

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.recyclerview.widget.LinearLayoutManager
import com.example.pick_dream.databinding.FragmentLlmBinding
import com.example.pick_dream.R
import androidx.navigation.fragment.findNavController
import androidx.navigation.NavOptions
import androidx.activity.OnBackPressedCallback
import androidx.lifecycle.lifecycleScope
import com.example.pick_dream.notification.PickDreamNotificationManager
import com.example.pick_dream.repository.UserRepository
import com.example.pick_dream.ui.home.reservation.ReservationRepository
import com.google.firebase.auth.FirebaseAuth
import kotlinx.coroutines.launch
import org.json.JSONObject

class LlmFragment : Fragment() {
    private var _binding: FragmentLlmBinding? = null
    private val binding get() = _binding!!

    private val messages = mutableListOf<LlmMessage>()
    private lateinit var adapter: LlmAdapter

    private val suggestions = listOf(
        "6명이서 이용하기 좋은 강의실은 어디야?",
        "지금 예약 가능한 강의실 알려줘",
        "전자칠판 있는 강의실 추천해줘",
        "빔프로젝터 있는 강의실 추천해줘"
    )
    private var isFirstMessageSent = false

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentLlmBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        val bottomNav = requireActivity().findViewById<View>(R.id.nav_view)
        bottomNav?.visibility = View.GONE

        binding.toolbarTitle.text = "AI 예약"

        binding.btnBack.setOnClickListener {
            navigateToHome()
        }

        requireActivity().onBackPressedDispatcher.addCallback(
            viewLifecycleOwner,
            object : OnBackPressedCallback(true) {
                override fun handleOnBackPressed() {
                    navigateToHome()
                }
            }
        )

        adapter = LlmAdapter(messages) { quickReply, displayText ->
            sendMessage(quickReply, displayText)
        }
        binding.recyclerView.layoutManager = LinearLayoutManager(requireContext())
        binding.recyclerView.adapter = adapter

        showSuggestions()

        binding.buttonSend.setOnClickListener {
            sendMessage()
        }
    }

    private fun navigateToHome() {
        findNavController().navigate(
            R.id.homeFragment,
            null,
            NavOptions.Builder()
                .setPopUpTo(R.id.homeFragment, false)
                .build()
        )
    }

    private fun showSuggestions() {
        binding.layoutSuggestions.removeAllViews()
        suggestions.forEach { text ->
            val chip = LayoutInflater.from(context)
                .inflate(R.layout.item_suggestion_chip, binding.layoutSuggestions, false) as TextView
            chip.text = text
            chip.setOnClickListener {
                binding.editTextMessage.setText(text)
                binding.editTextMessage.setSelection(text.length)
            }
            binding.layoutSuggestions.addView(chip)
        }
        binding.suggestionScroll.visibility = View.VISIBLE
    }

    private fun hideSuggestions() {
        binding.suggestionScroll.visibility = View.GONE
    }

    private fun sendMessage(overrideText: String? = null, displayText: String? = null) {
        val text = (overrideText ?: binding.editTextMessage.text.toString()).trim()
        if (text.isNotEmpty()) {
            messages.add(LlmMessage(displayText ?: text, true))
            adapter.notifyItemInserted(messages.size - 1)
            binding.recyclerView.scrollToPosition(messages.size - 1)
            if (overrideText == null) {
                binding.editTextMessage.text.clear()
            }

            if (!isFirstMessageSent) {
                hideSuggestions()
                isFirstMessageSent = true
            }

            val user = FirebaseAuth.getInstance().currentUser
            user?.getIdToken(true)?.addOnSuccessListener { result ->
                val idToken = result.token ?: ""

                FirebaseFunctionService.sendMessageToFunction(
                    message = text,
                    idToken = idToken,
                    onSuccess = { reply ->
                        requireActivity().runOnUiThread {
                            val botMessage = parseBotMessage(reply)
                            messages.add(botMessage)
                            adapter.notifyItemInserted(messages.size - 1)
                            binding.recyclerView.scrollToPosition(messages.size - 1)
                            handleNotificationSideEffects(botMessage.text)
                        }
                    },
                    onFailure = { e ->
                        requireActivity().runOnUiThread {
                            messages.add(LlmMessage("오류 발생: ${e.localizedMessage}", false))
                            adapter.notifyItemInserted(messages.size - 1)
                        }
                    }
                )
            } ?: run {
                messages.add(LlmMessage("로그인이 필요합니다.", false))
                adapter.notifyItemInserted(messages.size - 1)
            }
        }
    }

    private fun parseBotMessage(raw: String): LlmMessage {
        return runCatching {
            val json = JSONObject(raw)
            val text = json.optString("text", raw)
            val title = json.optString("title").takeIf { it.isNotBlank() }
            val cardsJson = json.optJSONArray("cards")
            val cards = mutableListOf<LlmCard>()

            if (cardsJson != null) {
                for (i in 0 until cardsJson.length()) {
                    val cardJson = cardsJson.optJSONObject(i) ?: continue
                    val actionsJson = cardJson.optJSONArray("actions")
                    val actions = mutableListOf<LlmAction>()

                    if (actionsJson != null) {
                        for (j in 0 until actionsJson.length()) {
                            val actionJson = actionsJson.optJSONObject(j) ?: continue
                            val label = actionJson.optString("label")
                            val message = actionJson.optString("message")
                            if (label.isBlank() || message.isBlank()) continue
                            actions.add(
                                LlmAction(
                                    label = label,
                                    message = message,
                                    displayText = actionJson.optString("displayText", label)
                                )
                            )
                        }
                    }

                    val roomName = cardJson.optString("roomName")
                    if (roomName.isBlank()) continue
                    cards.add(
                        LlmCard(
                            type = cardJson.optString("type"),
                            roomName = roomName,
                            description = cardJson.optString("description"),
                            startTime = cardJson.optString("startTime"),
                            endTime = cardJson.optString("endTime"),
                            participants = cardJson.optString("participants").takeIf { it.isNotBlank() },
                            actions = actions
                        )
                    )
                }
            }

            LlmMessage(text = text, isUser = false, title = title, cards = cards)
        }.getOrElse {
            LlmMessage(raw, false)
        }
    }

    private fun handleNotificationSideEffects(reply: String) {
        when {
            "취소되었습니다" in reply -> {
                PickDreamNotificationManager.showReservationCanceled(
                    requireContext(),
                    extractRoomName(reply)
                )
                scheduleUpcomingUsageReminders()
            }

            "예약되었습니다" in reply || "변경되었습니다" in reply -> {
                PickDreamNotificationManager.showReservationComplete(
                    requireContext(),
                    extractRoomName(reply)
                )
                scheduleUpcomingUsageReminders()
            }
        }
    }

    private fun scheduleUpcomingUsageReminders() {
        viewLifecycleOwner.lifecycleScope.launch {
            val studentId = UserRepository.getCurrentStudentId()
            if (studentId.isNullOrBlank() || !isAdded) return@launch

            val reservations = ReservationRepository.getReservationsByUser(studentId)
            if (!isAdded) return@launch

            reservations.forEach { reservation ->
                PickDreamNotificationManager.scheduleUsageReminder(requireContext(), reservation)
            }
        }
    }

    private fun extractRoomName(text: String): String? {
        val match = Regex("""([0-9]{3,4}\s*강의실)""").find(text)
        return match?.value?.replace("\\s+".toRegex(), " ")
    }

    override fun onDestroyView() {
        super.onDestroyView()
        val bottomNav = requireActivity().findViewById<View>(R.id.nav_view)
        bottomNav?.visibility = View.VISIBLE
        _binding = null
    }
}
