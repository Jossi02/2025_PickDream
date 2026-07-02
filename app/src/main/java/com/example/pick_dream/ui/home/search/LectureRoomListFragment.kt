package com.example.pick_dream.ui.home.search

import android.content.Context
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.InputMethodManager
import androidx.fragment.app.Fragment
import androidx.navigation.fragment.findNavController
import androidx.recyclerview.widget.LinearLayoutManager
import com.example.pick_dream.R
import com.example.pick_dream.databinding.FragmentLectureRoomListBinding
import com.example.pick_dream.model.LectureRoom

class LectureRoomListFragment : Fragment() {
    private var _binding: FragmentLectureRoomListBinding? = null
    private val binding get() = _binding!!
    private lateinit var adapter: LectureRoomAdapter
    private var allItems = listOf<ListItem>()

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View {
        _binding = FragmentLectureRoomListBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        setupRecyclerView()
        setupSearch()
        setupFilterButtons()
        observeLectureRooms()

        val initialQuery = arguments?.getString("initialSearchQuery")
        if (!initialQuery.isNullOrBlank()) {
            binding.etSearch.setText(initialQuery)
        }

        binding.btnBack.setOnClickListener {
            findNavController().popBackStack()
        }

        requireActivity().findViewById<View>(R.id.nav_view)?.visibility = View.GONE

        // 데이터는 MainActivity에서 미리 로드하므로 여기서는 호출할 필요가 없습니다.
        // LectureRoomRepository.fetchRooms()
        // LectureRoomRepository.fetchFavoriteIds()
    }
    
    private fun setupSearch() {
        binding.etSearch.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                filterRooms(s.toString())
            }
            override fun afterTextChanged(s: Editable?) {}
        })
    }

    private fun setupFilterButtons() {
        binding.btnFilterBeam.setOnClickListener { setQueryAndFilter("빔프로젝터") }
        binding.btnFilterMic.setOnClickListener { setQueryAndFilter("마이크") }
        binding.btnFilterOutlet.setOnClickListener { setQueryAndFilter("콘센트") }
        binding.btnFilterScreen.setOnClickListener { setQueryAndFilter("스크린") }
    }

    private fun setQueryAndFilter(query: String) {
        binding.etSearch.setText(query)
    }

    private fun setupRecyclerView() {
        adapter = LectureRoomAdapter(
            mutableListOf(),
            onItemClick = { room ->
                val action = LectureRoomListFragmentDirections
                    .actionLectureRoomListFragmentToLectureRoomDetailFragment(
                        roomName = room.name,
                        building = "${room.buildingName} (${room.buildingDetail})",
                        buildingName = room.buildingName,
                        buildingDetail = room.buildingDetail
                    )
                findNavController().navigate(action)
            },
            onFavoriteClick = { room ->
                LectureRoomRepository.toggleFavorite(room.id)
            }
        )
        binding.rvLectureRooms.layoutManager = LinearLayoutManager(context)
        binding.rvLectureRooms.adapter = adapter
    }

    private fun observeLectureRooms() {
        LectureRoomRepository.lectureRoomsWithFavorites.observe(viewLifecycleOwner) { items ->
            Log.d("LectureRoomListFragment", "Observed ${items.size} items")
            allItems = items
            filterRooms(binding.etSearch.text.toString())
        }
    }
    
    private fun filterRooms(query: String?) {
        val filteredList = if (query.isNullOrEmpty()) {
            allItems
        } else {
            val normalizedQuery = query.toSearchKey()
            val filteredItems = mutableListOf<ListItem>()
            var currentHeader: ListItem.HeaderItem? = null
            val roomsUnderCurrentHeader = mutableListOf<ListItem.RoomItem>()

            for (item in allItems) {
                when (item) {
                    is ListItem.HeaderItem -> {
                        if (currentHeader != null && roomsUnderCurrentHeader.isNotEmpty()) {
                            filteredItems.add(currentHeader)
                            filteredItems.addAll(roomsUnderCurrentHeader)
                        }
                        currentHeader = item
                        roomsUnderCurrentHeader.clear()
                    }
                    is ListItem.RoomItem -> {
                        val room = item.lectureRoom
                        if (room.matchesSearch(normalizedQuery, currentHeader?.buildingName)) {
                            roomsUnderCurrentHeader.add(item)
                        }
                    }
                }
            }
            if (currentHeader != null && roomsUnderCurrentHeader.isNotEmpty()) {
                filteredItems.add(currentHeader)
                filteredItems.addAll(roomsUnderCurrentHeader)
            }
            filteredItems
        }
        adapter.submitList(filteredList)
    }

    private fun LectureRoom.matchesSearch(normalizedQuery: String, headerName: String?): Boolean {
        if (normalizedQuery.isBlank()) return true

        return if (normalizedQuery.all { it.isDigit() }) {
            matchesNumericSearch(normalizedQuery)
        } else {
            searchableTextTerms(headerName).any { term ->
                term.toSearchKey().contains(normalizedQuery)
            }
        }
    }

    private fun LectureRoom.matchesNumericSearch(normalizedQuery: String): Boolean {
        val roomDigits = name.filter { it.isDigit() }
        val buildingNumber = buildingNumber()
        val generatedRoomAlias = if (buildingNumber.isNotBlank() && roomDigits.isNotBlank()) {
            buildingNumber + roomDigits
        } else {
            ""
        }
        val numericDocumentId = id.takeIf { it.isNotBlank() && it.all { char -> char.isDigit() } }.orEmpty()

        if (normalizedQuery.length == 1) {
            return buildingNumber == normalizedQuery || generatedRoomAlias.startsWith(normalizedQuery)
        }

        return listOf(roomDigits, generatedRoomAlias, numericDocumentId)
            .filter { it.isNotBlank() }
            .any { it.contains(normalizedQuery) }
    }

    private fun LectureRoom.searchableTextTerms(headerName: String?): List<String> {
        val roomDigits = name.filter { it.isDigit() }
        val buildingNumber = buildingNumber()
        val generatedRoomAlias = if (buildingNumber.isNotBlank() && roomDigits.isNotBlank()) {
            buildingNumber + roomDigits
        } else {
            ""
        }
        val numericDocumentId = id.takeIf { it.isNotBlank() && it.all { char -> char.isDigit() } }.orEmpty()

        return buildList {
            add(numericDocumentId)
            add(name)
            add(roomDigits)
            add(generatedRoomAlias)
            add("${generatedRoomAlias}호")
            add("${generatedRoomAlias}강의실")
            add(buildingName)
            add(buildingDetail)
            add(displayBuildingName)
            add(headerName.orEmpty())
            addAll(equipment)
        }.filter { it.isNotBlank() }
    }

    private fun LectureRoom.buildingNumber(): String {
        val sources = listOf(buildingDetail, displayBuildingName)
        for (source in sources) {
            val match = Regex("""(\d+)\s*강의동""").find(source)
            if (match != null) return match.groupValues[1]
        }

        return when (buildingName) {
            "예지관" -> "4"
            "덕문관" -> "5"
            "집현관" -> "7"
            else -> ""
        }
    }

    private fun String.toSearchKey(): String {
        return lowercase()
            .replace("\\s+".toRegex(), "")
    }
    
    private fun hideKeyboard(view: View) {
        val imm = view.context.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        imm.hideSoftInputFromWindow(view.windowToken, 0)
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
        requireActivity().findViewById<View>(R.id.nav_view)?.visibility = View.VISIBLE
    }
}
