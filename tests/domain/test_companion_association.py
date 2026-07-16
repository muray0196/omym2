"""
Summary: Tests pure companion source association and target derivation.
Why: Prevents lyrics and artwork from being duplicated or misclassified as leftovers.
"""

from __future__ import annotations

from omym2.domain.models.companion_asset import CompanionAssetKind
from omym2.domain.services.companion_association import (
    CompanionAssociation,
    CompanionAudioCandidate,
    CompanionIssue,
    CompanionIssueCode,
    associate_companions,
)

ALBUM_DIRECTORY = "incoming/Album"
ARTWORK_SOURCE = f"{ALBUM_DIRECTORY}/Cover.JPG"
ARTWORK_TARGET = "Artist/Album/Cover.JPG"
FIRST_AUDIO_SOURCE = f"{ALBUM_DIRECTORY}/01.flac"
FIRST_AUDIO_TARGET = "Artist/Album/01.flac"
LYRICS_SOURCE = f"{ALBUM_DIRECTORY}/01.lrc"
LYRICS_TARGET = "Artist/Album/01.lrc"
SECOND_AUDIO_SOURCE = f"{ALBUM_DIRECTORY}/02.mp3"
SECOND_AUDIO_TARGET = "Artist/Album/02.mp3"


def test_lyrics_exact_stem_match_derives_owner_target_and_dependency() -> None:
    """One same-directory exact-stem audio owns lyrics at its planned target stem."""
    audio = CompanionAudioCandidate(FIRST_AUDIO_SOURCE, FIRST_AUDIO_TARGET)

    result = associate_companions((audio,), (LYRICS_SOURCE, f"{ALBUM_DIRECTORY}/notes.txt"))

    assert result.claimed_source_paths == frozenset({LYRICS_SOURCE})
    assert result.associations == (
        CompanionAssociation(
            kind=CompanionAssetKind.LYRICS,
            source_path=LYRICS_SOURCE,
            owner_audio_source_path=FIRST_AUDIO_SOURCE,
            target_path=LYRICS_TARGET,
            dependency_audio_source_paths=(FIRST_AUDIO_SOURCE,),
        ),
    )
    assert result.issues == ()


def test_lyrics_stem_matching_preserves_case_and_unicode_exactness() -> None:
    """Extension recognition is case-insensitive while stem ownership is case/Unicode exact."""
    composed_stem = "Café"
    decomposed_stem = "Café"
    audio_source = f"{ALBUM_DIRECTORY}/{composed_stem}.flac"
    exact_lyrics = f"{ALBUM_DIRECTORY}/{composed_stem}.LRC"
    case_mismatch = f"{ALBUM_DIRECTORY}/café.lrc"
    unicode_mismatch = f"{ALBUM_DIRECTORY}/{decomposed_stem}.lrc"
    audio = CompanionAudioCandidate(audio_source, f"Artist/Album/{composed_stem}.flac")

    result = associate_companions((audio,), (unicode_mismatch, exact_lyrics, case_mismatch))

    assert result.claimed_source_paths == frozenset({exact_lyrics})
    assert result.associations == (
        CompanionAssociation(
            kind=CompanionAssetKind.LYRICS,
            source_path=exact_lyrics,
            owner_audio_source_path=audio_source,
            target_path=f"Artist/Album/{composed_stem}.lrc",
            dependency_audio_source_paths=(audio_source,),
        ),
    )
    assert result.issues == (
        CompanionIssue(
            kind=CompanionAssetKind.LYRICS,
            source_path=unicode_mismatch,
            code=CompanionIssueCode.OWNER_MISSING,
            dependency_audio_source_paths=(),
        ),
        CompanionIssue(
            kind=CompanionAssetKind.LYRICS,
            source_path=case_mismatch,
            code=CompanionIssueCode.OWNER_MISSING,
            dependency_audio_source_paths=(),
        ),
    )


def test_lyrics_with_multiple_exact_stem_matches_are_claimed_as_ambiguous() -> None:
    """Multiple audio extensions with one stem protect lyrics but cannot select an owner."""
    first_audio = CompanionAudioCandidate(f"{ALBUM_DIRECTORY}/Song.flac", "Artist/Album/Song.flac")
    second_audio = CompanionAudioCandidate(f"{ALBUM_DIRECTORY}/Song.mp3", "Artist/Album/Song.mp3")
    lyrics_source = f"{ALBUM_DIRECTORY}/Song.lrc"

    result = associate_companions((second_audio, first_audio), (lyrics_source,))

    assert result.claimed_source_paths == frozenset({lyrics_source})
    assert result.associations == ()
    assert result.issues == (
        CompanionIssue(
            kind=CompanionAssetKind.LYRICS,
            source_path=lyrics_source,
            code=CompanionIssueCode.OWNER_AMBIGUOUS,
            dependency_audio_source_paths=(first_audio.source_path, second_audio.source_path),
        ),
    )


def test_owned_lyrics_without_audio_target_are_claimed_with_target_issue() -> None:
    """A known owner remains a dependency even when its Plan target is unavailable."""
    audio = CompanionAudioCandidate(FIRST_AUDIO_SOURCE, None)

    result = associate_companions((audio,), (LYRICS_SOURCE,))

    assert result.claimed_source_paths == frozenset({LYRICS_SOURCE})
    assert result.associations == (
        CompanionAssociation(
            kind=CompanionAssetKind.LYRICS,
            source_path=LYRICS_SOURCE,
            owner_audio_source_path=FIRST_AUDIO_SOURCE,
            target_path=None,
            dependency_audio_source_paths=(FIRST_AUDIO_SOURCE,),
        ),
    )
    assert result.issues == (
        CompanionIssue(
            kind=CompanionAssetKind.LYRICS,
            source_path=LYRICS_SOURCE,
            code=CompanionIssueCode.TARGET_MISSING,
            dependency_audio_source_paths=(FIRST_AUDIO_SOURCE,),
        ),
    )


def test_artwork_is_emitted_once_for_all_direct_sibling_audio() -> None:
    """Directory artwork uses the first source-relative audio owner and one shared target."""
    first_audio = CompanionAudioCandidate(FIRST_AUDIO_SOURCE, FIRST_AUDIO_TARGET)
    second_audio = CompanionAudioCandidate(SECOND_AUDIO_SOURCE, SECOND_AUDIO_TARGET)
    nested_audio = CompanionAudioCandidate(
        f"{ALBUM_DIRECTORY}/Disc/03.flac",
        "Artist/Album/03.flac",
    )

    result = associate_companions(
        (second_audio, nested_audio, first_audio),
        (ARTWORK_SOURCE, ARTWORK_SOURCE, f"{ALBUM_DIRECTORY}/Cover.gif"),
    )

    assert result.claimed_source_paths == frozenset({ARTWORK_SOURCE})
    assert result.associations == (
        CompanionAssociation(
            kind=CompanionAssetKind.ARTWORK,
            source_path=ARTWORK_SOURCE,
            owner_audio_source_path=FIRST_AUDIO_SOURCE,
            target_path=ARTWORK_TARGET,
            dependency_audio_source_paths=(FIRST_AUDIO_SOURCE, SECOND_AUDIO_SOURCE),
        ),
    )
    assert result.issues == ()


def test_artwork_with_missing_associated_target_has_typed_issue() -> None:
    """Every direct-sibling audio target must exist before artwork gets a target."""
    first_audio = CompanionAudioCandidate(FIRST_AUDIO_SOURCE, FIRST_AUDIO_TARGET)
    second_audio = CompanionAudioCandidate(SECOND_AUDIO_SOURCE, None)

    result = associate_companions((second_audio, first_audio), (ARTWORK_SOURCE,))

    assert result.claimed_source_paths == frozenset({ARTWORK_SOURCE})
    assert result.associations == (
        CompanionAssociation(
            kind=CompanionAssetKind.ARTWORK,
            source_path=ARTWORK_SOURCE,
            owner_audio_source_path=FIRST_AUDIO_SOURCE,
            target_path=None,
            dependency_audio_source_paths=(FIRST_AUDIO_SOURCE, SECOND_AUDIO_SOURCE),
        ),
    )
    assert result.issues == (
        CompanionIssue(
            kind=CompanionAssetKind.ARTWORK,
            source_path=ARTWORK_SOURCE,
            code=CompanionIssueCode.TARGET_MISSING,
            dependency_audio_source_paths=(FIRST_AUDIO_SOURCE, SECOND_AUDIO_SOURCE),
        ),
    )


def test_artwork_with_different_target_parents_has_typed_issue() -> None:
    """Artwork cannot choose one shared location when sibling audio targets split directories."""
    first_audio = CompanionAudioCandidate(FIRST_AUDIO_SOURCE, FIRST_AUDIO_TARGET)
    second_audio = CompanionAudioCandidate(SECOND_AUDIO_SOURCE, "Artist/Other/02.mp3")

    result = associate_companions((first_audio, second_audio), (ARTWORK_SOURCE,))

    assert result.claimed_source_paths == frozenset({ARTWORK_SOURCE})
    assert result.associations[0].target_path is None
    assert result.issues == (
        CompanionIssue(
            kind=CompanionAssetKind.ARTWORK,
            source_path=ARTWORK_SOURCE,
            code=CompanionIssueCode.TARGET_PARENT_MISMATCH,
            dependency_audio_source_paths=(FIRST_AUDIO_SOURCE, SECOND_AUDIO_SOURCE),
        ),
    )


def test_orphan_lyrics_and_artwork_report_owner_issue_but_remain_unclaimed() -> None:
    """Unrelated media-like files stay available to later leftover classification."""
    orphan_artwork = "incoming/Other/photo.png"
    orphan_lyrics = "incoming/Other/notes.lrc"

    result = associate_companions((), (orphan_lyrics, orphan_artwork))

    assert result.claimed_source_paths == frozenset()
    assert result.associations == ()
    assert result.issues == (
        CompanionIssue(
            kind=CompanionAssetKind.LYRICS,
            source_path=orphan_lyrics,
            code=CompanionIssueCode.OWNER_MISSING,
            dependency_audio_source_paths=(),
        ),
        CompanionIssue(
            kind=CompanionAssetKind.ARTWORK,
            source_path=orphan_artwork,
            code=CompanionIssueCode.OWNER_MISSING,
            dependency_audio_source_paths=(),
        ),
    )
