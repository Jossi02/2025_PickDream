package com.example.pick_dream.ui.home.llm

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.view.LayoutInflater
import android.view.ViewGroup
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import com.google.android.material.button.MaterialButton
import androidx.recyclerview.widget.RecyclerView
import com.example.pick_dream.databinding.ItemLlmMessageBinding
import com.example.pick_dream.R
import com.google.android.material.card.MaterialCardView

class LlmAdapter(
    private val messages: List<LlmMessage>,
    private val onQuickReplyClick: (message: String, displayText: String) -> Unit = { _, _ -> }
) :
    RecyclerView.Adapter<LlmAdapter.LlmViewHolder>() {

    inner class LlmViewHolder(val binding: ItemLlmMessageBinding) : RecyclerView.ViewHolder(binding.root)

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): LlmViewHolder {
        val inflater = LayoutInflater.from(parent.context)
        val binding = ItemLlmMessageBinding.inflate(inflater, parent, false)
        return LlmViewHolder(binding)
    }

    override fun onBindViewHolder(holder: LlmViewHolder, position: Int) {
        val message = messages[position]
        val context = holder.itemView.context

        holder.binding.reservationCardsContainer.removeAllViews()
        holder.binding.reservationCardsContainer.visibility = View.GONE
        holder.binding.quickActionsContainer.removeAllViews()
        holder.binding.quickActionsContainer.visibility = View.GONE
        holder.binding.textMessage.visibility = View.VISIBLE

        if (message.isUser) {
            holder.binding.textMessage.text = message.text
            holder.binding.layoutRoot.gravity = Gravity.END
            holder.binding.textMessage.setBackgroundResource(R.drawable.bg_rounded_16dp)
            holder.binding.textMessage.backgroundTintList = ColorStateList.valueOf(Color.parseColor("#6391EE"))
            holder.binding.textMessage.setTextColor(context.getColor(android.R.color.white))
            holder.binding.imageBotIcon.visibility = android.view.View.GONE
        } else {
            holder.binding.layoutRoot.gravity = Gravity.START
            holder.binding.imageBotIcon.visibility = android.view.View.VISIBLE

            val sourceCards = message.cards.ifEmpty {
                LegacyLlmContentParser.parseCards(message.text)
            }
            val reservations = sourceCards.map { it.toReservationCard() }
            if (reservations.isNotEmpty()) {
                holder.binding.textMessage.visibility = View.GONE
                holder.binding.reservationCardsContainer.visibility = View.VISIBLE
                val headerText = message.title?.takeIf { it.isNotBlank() }
                    ?: LegacyLlmContentParser.headerText(message.text)
                addReservationHeader(context, holder.binding.reservationCardsContainer, headerText)
                reservations.forEach { reservation ->
                    holder.binding.reservationCardsContainer.addView(createReservationCard(context, reservation))
                }
            } else {
                holder.binding.textMessage.text = message.text
                holder.binding.textMessage.setBackgroundResource(R.drawable.bg_rounded_16dp)
                holder.binding.textMessage.backgroundTintList = ColorStateList.valueOf(Color.parseColor("#F7F9FF"))
                holder.binding.textMessage.setTextColor(context.getColor(android.R.color.black))
            }

            val quickActions = if (reservations.any { !it.actionLabel.isNullOrBlank() }) {
                emptyList()
            } else {
                LegacyLlmContentParser.parseQuickActions(message.text)
            }
            if (quickActions.isNotEmpty()) {
                holder.binding.quickActionsContainer.visibility = View.VISIBLE
                quickActions.forEach { action ->
                    holder.binding.quickActionsContainer.addView(createQuickActionButton(context, action))
                }
            }
        }
    }

    override fun getItemCount() = messages.size

    private data class ReservationCard(
        val roomName: String,
        val startTime: String,
        val endTime: String,
        val participants: String?,
        val actionLabel: String? = null,
        val actionMessage: String? = null,
        val actionDisplayText: String? = null
    )

    private fun LlmCard.toReservationCard(): ReservationCard {
        val action = actions.firstOrNull()
        val displayStartTime = description.ifBlank { startTime }
        return ReservationCard(
            roomName = roomName,
            startTime = simplifyKoreanDateTime(displayStartTime),
            endTime = if (description.isBlank()) simplifyKoreanDateTime(endTime) else "",
            participants = participants?.takeIf { it.isNotBlank() },
            actionLabel = action?.label,
            actionMessage = action?.message,
            actionDisplayText = action?.displayText
        )
    }

    private fun simplifyKoreanDateTime(value: String): String {
        return value
            .replace(Regex("\\s+\\d+초\\s+UTC\\+9"), "")
            .replace(Regex("\\s+UTC\\+9"), "")
            .trim()
    }

    private fun addReservationHeader(context: Context, container: LinearLayout, title: String) {
        val header = TextView(context).apply {
            text = title
            setTextColor(Color.parseColor("#222222"))
            textSize = 16f
            typeface = android.graphics.Typeface.DEFAULT_BOLD
            setPadding(dp(context, 4), 0, dp(context, 4), dp(context, 8))
        }
        container.addView(header)
    }

    private fun createQuickActionButton(context: Context, action: LlmAction): View {
        return MaterialButton(context, null, com.google.android.material.R.attr.materialButtonOutlinedStyle).apply {
            text = action.label
            textSize = 15f
            isAllCaps = false
            cornerRadius = dp(context, 10)
            strokeWidth = dp(context, 1)
            strokeColor = ColorStateList.valueOf(Color.parseColor("#5E8CFF"))
            setTextColor(Color.parseColor("#3F63C5"))
            backgroundTintList = ColorStateList.valueOf(Color.WHITE)
            minHeight = dp(context, 44)
            setPadding(dp(context, 12), 0, dp(context, 12), 0)
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                bottomMargin = dp(context, 8)
            }
            setOnClickListener {
                onQuickReplyClick(action.message, action.displayText)
            }
        }
    }

    private fun createReservationCard(context: Context, reservation: ReservationCard): View {
        val card = MaterialCardView(context).apply {
            radius = dp(context, 12).toFloat()
            cardElevation = dp(context, 1).toFloat()
            setCardBackgroundColor(Color.parseColor("#F7F9FF"))
            strokeColor = Color.parseColor("#5E8CFF")
            strokeWidth = dp(context, 1)
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                bottomMargin = dp(context, 10)
            }
        }

        val content = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(context, 14), dp(context, 12), dp(context, 14), dp(context, 12))
        }

        val room = TextView(context).apply {
            text = reservation.roomName
            setTextColor(Color.parseColor("#222222"))
            textSize = 17f
            typeface = android.graphics.Typeface.DEFAULT_BOLD
        }

        val time = TextView(context).apply {
            text = if (reservation.endTime.isBlank()) {
                reservation.startTime
            } else {
                "${reservation.startTime}\n~ ${reservation.endTime}"
            }
            setTextColor(Color.parseColor("#444444"))
            textSize = 14f
            setPadding(0, dp(context, 6), 0, 0)
        }

        content.addView(room)
        content.addView(time)

        reservation.participants?.takeIf { it.isNotBlank() }?.let {
            val participants = TextView(context).apply {
                text = "인원: $it"
                setTextColor(Color.parseColor("#444444"))
                textSize = 14f
                setPadding(0, dp(context, 4), 0, 0)
            }
            content.addView(participants)
        }

        if (!reservation.actionLabel.isNullOrBlank() && !reservation.actionMessage.isNullOrBlank()) {
            content.addView(
                createQuickActionButton(
                    context,
                    LlmAction(
                        label = reservation.actionLabel,
                        message = reservation.actionMessage,
                        displayText = reservation.actionDisplayText ?: reservation.actionLabel
                    )
                )
            )
        }

        card.addView(content)
        return card
    }

    private fun dp(context: Context, value: Int): Int {
        return (value * context.resources.displayMetrics.density).toInt()
    }
}
