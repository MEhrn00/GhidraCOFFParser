# COFF file parser which will map missing sections/headers, add COFF types, annotate xrefs
# and perform relocations.
# @author Matt Ehrnschwender
# @category Analysis
# @menupath Analysis.One Shot.COFF Parser
# @toolbar

import jarray
import struct
from ghidra.program.model.data import (
    ArrayDataType,
    CategoryPath,
    CharDataType,
    DataTypeConflictHandler,
    ShortDataType,
    ShortDataType,
    StructureDataType,
    TerminatedStringDataType,
    UnionDataType,
    UnsignedCharDataType,
    UnsignedIntegerDataType,
    UnsignedShortDataType,
)
from ghidra.util.exception import CancelledException
from ghidra.program.model.symbol import RefType, SourceType
from ghidra.program.model.address import AddressSet
from ghidra.app.cmd.disassemble import X86_64DisassembleCommand

# Helper for converting a signed byte to unsigned
ubyte = lambda x: struct.unpack("B", struct.pack("b", x))[0]

# Object for interacting with the program's memory mappings
memory_map = currentProgram.getMemory()

# Object for interacting with Ghidra's listing view
listing = currentProgram.getListing()

# Object for interacting with memory references
ref_mgr = currentProgram.getReferenceManager()

# Converts an integer to a Ghidra `Address` type
Address = (
    lambda x: currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(x)
)

# Type definition for the COFF file header
COFF_HEADER_TYPE = StructureDataType(CategoryPath("/COFFDefs"), "COFFHeader", 0)

# Type definition for the COFF file header
COFF_OPTIONAL_HEADER_TYPE = StructureDataType(CategoryPath("/COFFDefs"), "COFFOptionalHeader", 0)

# Type definition for the COFF section header
COFF_SECTION_HEADER_TYPE = StructureDataType(
    CategoryPath("/COFFDefs"), "COFFSectionHeader", 0
)

# Type definition for a COFF Symbol Table entry
COFF_SYMBOL_TYPE = StructureDataType(CategoryPath("/COFFDefs"), "COFFSymbol", 0)

# Type definition for a COFF symbol name existing in the string table
COFF_SYMBOL_LONG_NAME_TYPE = StructureDataType(
    CategoryPath("/COFFDefs"), "COFFSymbolLongName", 0
)

# Type definition for the COFF Symbol Table Name
COFF_SYMBOL_NAME_TYPE = UnionDataType(CategoryPath("/COFFDefs"), "COFFSymbolName")

# Type definion for a COFF relocation entry
COFF_RELOC_TYPE = StructureDataType(CategoryPath("/COFFDefs"), "COFFReloc", 0)

# Raw data of the COFF file being parsed
COFF_DATA = bytearray()


def add_member(s, ty, n, c):
    """
    Add a member to a structure data type.

    Parameters:
     * s - Structure to add the member to
     * ty - Data type for the structure member
     * n - Name of the structure member
     * c - Comment for the structure member
    """
    if (
        isinstance(ty, ArrayDataType)
        or isinstance(ty, StructureDataType)
        or isinstance(ty, UnionDataType)
    ):
        s.add(ty, ty.getLength(), n, c)
    else:
        s.add(ty.dataType, ty.dataType.getLength(), n, c)


def add_coff_types(tm):
    """
    Creates all of the COFF types and adds them to Ghidra type database (under [program] -> COFFDefs)

    Parameters:
     * tm - Ghidra type manager
    """

    coff_types = []

    """
    /* sizeof == 20 */
    struct COFFHeader {
        uint16_t Machine;
        uint16_t NumberOfSections;
        uint32_t TimeDateStamp;
        uint32_t PointerToSymbolTable;
        uint32_t NumberOfSymbols;
        uint16_t SizeOfOptionalHeader;
        uint16_t Characteristics;
    };
    """

    add_member(
        COFF_HEADER_TYPE,  # Structure
        UnsignedShortDataType,  # Member type
        "Machine",  # Member name
        "Machine ID",  # Member comment
    )

    add_member(
        COFF_HEADER_TYPE,  # Structure
        UnsignedShortDataType,  # Member type
        "NumberOfSections",  # Member name
        "Number of sections",  # Member comment
    )

    add_member(
        COFF_HEADER_TYPE,  # Structure
        UnsignedIntegerDataType,  # Member type
        "TimeDateStamp",  # Member name
        "Timestamp",  # Member comment
    )

    add_member(
        COFF_HEADER_TYPE,  # Structure
        UnsignedIntegerDataType,  # Member type
        "PointerToSymbolTable",  # Member name
        "Pointer to the symbol table",  # Member comment
    )

    add_member(
        COFF_HEADER_TYPE,  # Structure
        UnsignedIntegerDataType,  # Member type
        "NumberOfSymbols",  # Member name
        "Number of symbols",  # Member comment
    )

    add_member(
        COFF_HEADER_TYPE,  # Structure
        UnsignedShortDataType,  # Member type
        "SizeOfOptionalHeader",  # Member name
        "Size of the optional header",  # Member comment
    )

    add_member(
        COFF_HEADER_TYPE,  # Structure
        UnsignedShortDataType,  # Member type
        "Characteristics",  # Member name
        "Characteristics of the file",  # Member comment
    )

    coff_types.append(COFF_HEADER_TYPE)

    """
    /* sizeof == 28 */
    struct COFFOptionalHeader {
        int16_t  magic;          /* Magic Number                    */
        int16_t  vstamp;         /* Version stamp                   */
        uint32_t tsize;          /* Text size in bytes              */
        uint32_t dsize;          /* Initialised data size           */
        uint32_t bsize;          /* Uninitialised data size         */
        uint32_t entry;          /* Entry point                     */
        uint32_t text_start;     /* Base of Text used for this file */
        uint32_t data_start;     /* Base of Data used for this file */
    };
    """
    add_member(
        COFF_OPTIONAL_HEADER_TYPE,  # Structure
        ShortDataType,  # Member type
        "magic",  # Member name
        "Magic Number",  # Member comment
    )

    add_member(
        COFF_OPTIONAL_HEADER_TYPE,  # Structure
        ShortDataType,  # Member type
        "vstamp",  # Member name
        "Version stamp",  # Member comment
    )

    add_member(
        COFF_OPTIONAL_HEADER_TYPE,  # Structure
        UnsignedIntegerDataType,  # Member type
        "tsize",  # Member name
        "Text size in bytes",  # Member comment
    )


    add_member(
        COFF_OPTIONAL_HEADER_TYPE,  # Structure
        UnsignedIntegerDataType,  # Member type
        "dsize",  # Member name
        "Initialised data size",  # Member comment
    )

    add_member(
        COFF_OPTIONAL_HEADER_TYPE,  # Structure
        UnsignedIntegerDataType,  # Member type
        "bsize",  # Member name
        "Uninitialised data size ",  # Member comment
    )

    add_member(
        COFF_OPTIONAL_HEADER_TYPE,  # Structure
        UnsignedIntegerDataType,  # Member type
        "entry",  # Member name
        "Entry point",  # Member comment
    )

    add_member(
        COFF_OPTIONAL_HEADER_TYPE,  # Structure
        UnsignedIntegerDataType,  # Member type
        "text_start",  # Member name
        "Base of Text used for this file",  # Member comment
    )

    add_member(
        COFF_OPTIONAL_HEADER_TYPE,  # Structure
        UnsignedIntegerDataType,  # Member type
        "data_start",  # Member name
        "Base of Data used for this file",  # Member comment
    )

    coff_types.append(COFF_OPTIONAL_HEADER_TYPE)
    """
    /* sizeof == 40 */
    struct COFFSectionHeader {
        char Name[8];
        uint32_t VirtualSize;
        uint32_t VirtualAddress;
        uint32_t SizeOfRawData;
        uint32_t PointerToRawData;
        uint32_t PointerToRelocations;
        uint32_t PointerToLineNumbers;
        uint16_t NumberOfRelocations;
        uint16_t NumberOfLinenumbers;
        uint32_t Characteristics;
    };
    """

    add_member(
        COFF_SECTION_HEADER_TYPE,  # Structure
        ArrayDataType(CharDataType.dataType, 8, 1),  # Member type
        "Name",  # Member name
        "Name of the section",  # Member comment
    )

    add_member(
        COFF_SECTION_HEADER_TYPE,  # Structure
        UnsignedIntegerDataType,  # Member type
        "VirtualSize",  # Member name
        "Virtual size of the section",  # Member comment
    )

    add_member(
        COFF_SECTION_HEADER_TYPE,  # Structure
        UnsignedIntegerDataType,  # Member type
        "VirtualAddress",  # Member name
        "Virtual address of the section",  # Member comment
    )

    add_member(
        COFF_SECTION_HEADER_TYPE,  # Structure
        UnsignedIntegerDataType,  # Member type
        "SizeOfRawData",  # Member name
        "Size of the section data",  # Member comment
    )

    add_member(
        COFF_SECTION_HEADER_TYPE,  # Structure
        UnsignedIntegerDataType,  # Member type
        "PointerToRawData",  # Member name
        "Pointer to the raw section data",  # Member comment
    )

    add_member(
        COFF_SECTION_HEADER_TYPE,  # Structure
        UnsignedIntegerDataType,  # Member type
        "PointerToRelocations",  # Member name
        "Pointer to the relocation table",  # Member comment
    )

    add_member(
        COFF_SECTION_HEADER_TYPE,  # Structure
        UnsignedIntegerDataType,  # Member type
        "PointerToLineNumbers",  # Member name
        "Pointer to the line numbers",  # Member comment
    )

    add_member(
        COFF_SECTION_HEADER_TYPE,  # Structure
        UnsignedShortDataType,  # Member type
        "NumberOfRelocations",  # Member name
        "Number of relocations in the section",  # Member comment
    )

    add_member(
        COFF_SECTION_HEADER_TYPE,  # Structure
        UnsignedShortDataType,  # Member type
        "NumberOfLinenumbers",  # Member name
        "Number of line numbers",  # Member comment
    )

    add_member(
        COFF_SECTION_HEADER_TYPE,  # Structure
        UnsignedIntegerDataType,  # Member type
        "Characteristics",  # Member name
        "Characteristics of the section",  # Member comment
    )

    coff_types.append(COFF_SECTION_HEADER_TYPE)

    """
    /* sizeof == 18 */
    struct COFFSymbol {
        union COFFSymbolName {
            char ShortName[8];

            struct COFFSymbolLongName {
                uint32_t Zeroes;
                uint32_t Offset;
            };
        };

        uint32_t Value;
        int16_t SectionNumber;
        uint16_t Type;
        uint8_t StorageClass;
        uint8_t NumberOfAuxSymbols;
    };
    """

    add_member(
        COFF_SYMBOL_LONG_NAME_TYPE,  # Structure
        UnsignedIntegerDataType,  # Member type
        "Zeroes",  # Member name
        "A field that is set to all zeros if the name is longer than 8 bytes",  # Member comment
    )

    add_member(
        COFF_SYMBOL_LONG_NAME_TYPE,  # Structure
        UnsignedIntegerDataType,  # Member type
        "Offset",  # Member name
        "An offset into the string table",  # Member comment
    )

    coff_types.append(COFF_SYMBOL_NAME_TYPE)

    add_member(
        COFF_SYMBOL_NAME_TYPE,  # Structure
        ArrayDataType(CharDataType.dataType, 8, 1),  # Member type
        "ShortName",  # Member name
        "An array of 8 bytes. This array is padded with nulls on the right if the name is less than 8 bytes long",  # Member comment
    )

    add_member(
        COFF_SYMBOL_NAME_TYPE,  # Structure
        COFF_SYMBOL_LONG_NAME_TYPE,  # Member type
        "LongName",  # Member name
        "Name of the symbol if it resides in the string table",  # Member comment
    )

    coff_types.append(COFF_SYMBOL_NAME_TYPE)

    add_member(
        COFF_SYMBOL_TYPE,  # Structure
        COFF_SYMBOL_NAME_TYPE,  # Member type
        "Name",  # Member name
        "Name of the symbol",  # Member comment
    )

    add_member(
        COFF_SYMBOL_TYPE,  # Structure
        UnsignedIntegerDataType,  # Member type
        "Value",  # Member name
        "The value that is associated with the symbol",  # Member comment
    )

    add_member(
        COFF_SYMBOL_TYPE,  # Structure
        ShortDataType,  # Member type
        "SectionNumber",  # Member name
        "Signed integer that identifies the section",  # Member comment
    )

    add_member(
        COFF_SYMBOL_TYPE,  # Structure
        UnsignedShortDataType,  # Member type
        "Type",  # Member name
        "A number that represents the type of symbol",  # Member comment
    )

    add_member(
        COFF_SYMBOL_TYPE,  # Structure
        UnsignedCharDataType,  # Member type
        "StorageClass",  # Member name
        "An enumerated value that represents storage class",  # Member comment
    )

    add_member(
        COFF_SYMBOL_TYPE,  # Structure
        UnsignedCharDataType,  # Member type
        "NumberOfAuxSymbols",  # Member name
        "The number of auxiliary symbol table entries that follow this record",  # Member comment
    )

    coff_types.append(COFF_SYMBOL_TYPE)

    """
    struct COFFReloc {
        uint32_t VirtualAddress;
        uint32_t SymbolTableIndex;
        uint16_t Type;
    };
    """

    add_member(
        COFF_RELOC_TYPE,  # Structure
        UnsignedIntegerDataType,  # Member type
        "VirtualAddress",  # Member name
        "The address of the item to whic relocation is applied",  # Member comment
    )

    add_member(
        COFF_RELOC_TYPE,  # Structure
        UnsignedIntegerDataType,  # Member type
        "SymbolTableIndex",  # Member name
        "Zero-based index into the symbol table used for the relocation",  # Member comment
    )

    add_member(
        COFF_RELOC_TYPE,  # Structure
        UnsignedShortDataType,  # Member type
        "Type",  # Member name
        "Type of relocation to be performed",  # Member comment
    )

    coff_types.append(COFF_RELOC_TYPE)

    for ty in coff_types:
        tm.addDataType(ty, DataTypeConflictHandler.KEEP_HANDLER)


def read_bytes(addr, length):
    """
    Function to read a specified number of bytes from an address in Ghidra

    Parameters:
     * addr - Address to read from
     * length - Number of bytes to read
    """

    if isinstance(addr, int) or isinstance(addr, long):
        addr = Address(addr)

    buffer = jarray.zeros(length, "b")
    assert currentProgram.getMemory().getBytes(addr, buffer) == length
    return bytearray([ubyte(x) for x in buffer.tolist()])


def write_bytes(addr, data):
    """
    Function to write data to an address in Ghidra

    Parameters:
     * addr - Address to write to
     * length - Number of bytes to write
    """

    if isinstance(addr, int) or isinstance(addr, long):
        addr = Address(addr)

    buffer = jarray.array(data, "b")
    currentProgram.getMemory().setBytes(addr, buffer)


def apply_type(address, ty):
    """
    Applys a given type to an address

    Parameters:
     * address - Address to apply the type to
     * ty - Type to apply
    """

    start = Address(address)

    if isinstance(ty, TerminatedStringDataType):
        listing.clearCodeUnits(start, start.add(1), False)
        listing.createData(start, ty)
    else:
        end = Address(address + ty.getLength())
        listing.clearCodeUnits(start, end, False)
        listing.createData(start, ty, ty.getLength())


def reloc_section_header(header, section, perform_relocs):
    """
    Adds the `VirtualAddress` relocations to a section header

    Parameters:
     * header - Address of the COFF header
     * section - Pointer to the memory section being relocated in the header
     * perform_relocs - Perform relocations
    """
    section_no = struct.unpack("<H", COFF_DATA[2:4])[0]
    optional_header_size = struct.unpack("<H", COFF_DATA[0x10:0x12])[0]

    section_ptr = COFF_HEADER_TYPE.getLength() + optional_header_size
    for s in range(section_no):
        section_name = COFF_DATA[section_ptr : section_ptr + 8]
        section_name = "".join([chr(x) for x in section_name if x != 0])

        if section_name == section.getName():
            if perform_relocs:
                write_bytes(section_ptr + 8, struct.pack("<I", int(section.getSize())))

            # Reloc the `VirtualAddress` field since it's needed when performing inline
            # relocs
            section_va = int(section.getStart().toString("0x"), 16)
            write_bytes(
                section_ptr + 12,
                struct.pack("<I", section_va),
            )

            ref_mgr.addMemoryReference(
                Address(section_ptr + 12),
                Address(section_va),
                RefType.DATA,
                SourceType.USER_DEFINED,
                0,
            )

            break

        section_ptr += COFF_SECTION_HEADER_TYPE.getLength()


def apply_section_relocs(
    section_header,
    section_block,
    reloc_header,
    reloc_num,
    symbol_table,
    perform_relocs,
):
    """
    Apply relocations to a section

    Parameters:
     * section_header - Pointer to the array of section headers
     * section_block - Memory block being relocated
     * reloc_header - Pointer to the relocation array for the section
     * reloc_num - Number of relocs in the reloc array
     * symbol_table - Pointer to the COFF symbol table
     * perform_relocs - Bool signifying whether to perform relocs
    """

    if not isinstance(reloc_header, int) or not isinstance(reloc_header, long):
        reloc_header = int(reloc_header.toString("0x"), 16)

    # Iterate over each reloc entry in the reloc array
    for reloc_addr in range(reloc_header, reloc_header + (reloc_num * 10), 0xA):
        # Get the virtual address entry from the reloc structure
        virtual_address = struct.unpack("<I", read_bytes(reloc_addr, 4))[0]

        # Get the symbol table index from the reloc structure
        symbol_table_idx = struct.unpack("<I", read_bytes(reloc_addr + 4, 4))[0]

        # Get a pointer to the entry in the symbol table the reloc is associated with
        symbol_table_ptr = symbol_table.add(symbol_table_idx * 18)

        # Get the storage class for the reloc from the symbol table
        storage_class = struct.unpack("B", read_bytes(symbol_table_ptr.add(16), 1))[0]

        # Ghidra automatically handles `IMAGE_SYM_CLASS_EXTERNAL` relocs so just ignore
        # them
        if storage_class == 0x2:
            continue

        # Get the section number from the symbol table
        section_number = (
            struct.unpack("<H", read_bytes(symbol_table_ptr.add(12), 2))[0] - 1
        )

        # Get the address the symbol being relocated is at
        symbol_addr = int(
            section_block.getStart().add(virtual_address).toString("0x"), 16
        )

        # Get the relocation address for the symbol
        reloc_symbol_addr = struct.unpack(
            "<I",
            read_bytes(section_header + ((section_number * 40) + 12), 4),
        )[0]

        # Get the name of the section that the symbol is being relocated to
        reloc_section_name = "".join(
            [
                chr(x)
                for x in read_bytes(section_header + (section_number * 40), 8)
                if x != 0
            ]
        )

        # Get the memory block for the section being relocated to
        reloc_section_block = memory_map.getBlock(reloc_section_name)

        # Get the initial offset of the symbol being relocated
        initial_offset = struct.unpack("<I", read_bytes(symbol_addr, 4))[0]

        # Check if the symbol was already relocated
        already_relocd = reloc_section_block.contains(
            Address((symbol_addr + initial_offset + 4) & 0xFFFFFFFF)
        )

        # Get the machine ID to determine if the COFF is 64 bits or 32 bits. Used for
        # performing disassembly
        machine = struct.unpack("<H", read_bytes(0, 2))[0]
        if machine == 0x8664:
            size32 = False
        else:
            size32 = True

        # Perform relocs
        if perform_relocs:
            listing.clearCodeUnits(
                Address(symbol_addr), Address(symbol_addr + 1), False
            )

            if already_relocd:  # Symbol already reloc'd. Don't do anything
                pass
            else:  # Do the reloc
                rva = struct.unpack(
                    "<I",
                    struct.pack(
                        "<I", reloc_symbol_addr - symbol_addr - 4 + initial_offset
                    ),
                )[0]

                # The RVA needs to be big endian when patching the op code. For some
                # reason python2 needs to pack it as "little" endian here because I guess
                # "little" endian actually means "big" endian in python2 at this instance?
                write_bytes(symbol_addr, struct.pack("<I", rva))

            # Disassemble the code if it is in an executable region
            if section_block.isExecute():
                addr_set = AddressSet(
                    Address(symbol_addr - 3), Address(symbol_addr + 4)
                )

                currentProgram.getBookmarkManager().removeBookmarks(
                    addr_set, "Error", monitor
                )

                X86_64DisassembleCommand(addr_set, None, size32).applyTo(
                    currentProgram, monitor
                )

        else:  # Don't perform relocs
            if already_relocd:  # Symbol is reloc'd, need to revert it
                rva = struct.unpack("<I", read_bytes(symbol_addr, 4))[0]
                offset = (rva - reloc_symbol_addr + symbol_addr + 4) & 0xFFFFFFFF

                listing.clearCodeUnits(
                    Address(symbol_addr), Address(symbol_addr + 1), False
                )

                write_bytes(symbol_addr, struct.pack("<I", offset))

                if section_block.isExecute():
                    addr_set = AddressSet(
                        Address(symbol_addr - 3), Address(symbol_addr + 4)
                    )

                    currentProgram.getBookmarkManager().removeBookmarks(
                        addr_set, "Error", monitor
                    )

                    X86_64DisassembleCommand(addr_set, None, size32).applyTo(
                        currentProgram, monitor
                    )

            else:  # Symbol is not relocd so it can be left as is
                pass


def main(perform_relocs):
    """Main functionality of the script"""

    global COFF_DATA

    # Create a new type folder in the current program to hold the COFF type information
    type_manager = currentProgram.getDataTypeManager().createCategory(
        CategoryPath("/COFFDefs")
    )

    # Add COFF types to the Ghidra type database
    add_coff_types(type_manager)

    # Get the file bytes object for the program (used for doing file-backed mappings)
    coff_filebytes = currentProgram.getMemory().getAllFileBytes()[0]

    # Read in the COFF file bytes for parsing
    coff_bytes = jarray.zeros(coff_filebytes.getSize(), "b")
    assert (
        coff_filebytes.getOriginalBytes(0, coff_bytes) == coff_filebytes.getSize()
    ), "Failed to read COFF data"
    COFF_DATA = bytearray([ubyte(x) for x in coff_bytes.tolist()])

    # Get the number of sections from the header
    section_no = struct.unpack("<H", COFF_DATA[2:4])[0]

    # Get the optional header size
    optional_header_size = struct.unpack("<H", COFF_DATA[0x10:0x12])[0]

    # Create a memory mapping for the COFF file header
    if memory_map.getBlock("header") is not None:
        memory_map.removeBlock(memory_map.getBlock("header"), monitor)

    memory_map.createInitializedBlock(
        "header",  # Section name
        Address(0x0),  # Mapping address
        coff_filebytes,  # File backing
        0,  # File offset
        20 + optional_header_size + (section_no * 40),  # Size
        False,  # Overlay mapping
    )

    # Apply the COFF header type to the file header
    apply_type(0, COFF_HEADER_TYPE)

    if optional_header_size == 28:
        apply_type(20, COFF_OPTIONAL_HEADER_TYPE)

    # Apply the COFF section header array to the header
    apply_type(
        COFF_HEADER_TYPE.getLength() + optional_header_size,
        ArrayDataType(
            COFF_SECTION_HEADER_TYPE, section_no, COFF_SECTION_HEADER_TYPE.getLength()
        ),
    )

    # Apply relocations to the `VirtualAddress` and `VirtualSize` entry of the section headers
    header = memory_map.getBlock("header")
    sections = memory_map.getBlocks()
    for section in sections:
        if not section.isInitialized():
            continue
        reloc_section_header(header, section, perform_relocs)

    # Get the file offset into the symbol table and the number of entries in the symbol
    # table
    symbol_table_offset = struct.unpack("<I", COFF_DATA[8:0xC])[0]
    symbol_table_count = struct.unpack("<I", COFF_DATA[0xC:0x10])[0]
    symbol_table_size = symbol_table_count * 18
    if symbol_table_count == 0:
        return

    # Map the symbol table
    if memory_map.getBlock(".symtab") is not None:
        memory_map.removeBlock(memory_map.getBlock(".symtab"), monitor)

    memory_map.createInitializedBlock(
        ".symtab",  # Section name
        Address(0x4000),  # Mapping address
        coff_filebytes,  # File backing
        symbol_table_offset,  # File offset
        symbol_table_size,  # Size
        False,  # Overlay mapping
    )

    # Apply the array of symbol table types
    apply_type(
        0x4000,
        ArrayDataType(
            COFF_SYMBOL_TYPE, symbol_table_count, COFF_SYMBOL_TYPE.getLength()
        ),
    )

    # Relocate the COFF header `PointerToSymbolTable` entry to the mapped symbol table
    if perform_relocs:
        write_bytes(8, struct.pack("<I", 0x4000))
        ref_mgr.addMemoryReference(
            Address(8), Address(0x4000), RefType.DATA, SourceType.USER_DEFINED, 0
        )
    else:
        write_bytes(8, struct.pack("<I", 0))

    # Get the base address to map the string table. Round up to next 0x100 multiple
    string_table_addr = (0x4000 + symbol_table_size + 0xFF) & ~0xFF

    # Get the offset into the COFF file the string table resides
    string_table_offset = symbol_table_offset + symbol_table_size

    # Get the string table size
    string_table_size = struct.unpack(
        "<I", COFF_DATA[string_table_offset : string_table_offset + 4]
    )[0]

    # Remove existing string table mappings if there are any
    if memory_map.getBlock(".strtab") is not None:
        memory_map.removeBlock(memory_map.getBlock(".strtab"), monitor)

    # Map the string table
    memory_map.createInitializedBlock(
        ".strtab",  # Section name
        Address(string_table_addr),  # Mapping address
        coff_filebytes,  # File backing
        string_table_offset,  # File offset
        string_table_size,  # Size
        False,  # Overlay mapping
    )

    file_idx = symbol_table_offset

    # Change the string table entries to `TerminatedCString` types
    for addr in range(0x4000, 0x4000 + symbol_table_size, 18):
        zeroes = struct.unpack("<I", COFF_DATA[file_idx : file_idx + 4])[0]

        if zeroes == 0:
            offset = struct.unpack("<I", COFF_DATA[file_idx + 4 : file_idx + 8])[0]
            if offset != 0:
                apply_type(
                    string_table_addr + offset, TerminatedStringDataType.dataType
                )
                if perform_relocs:
                    write_bytes(addr + 4, struct.pack("<I", string_table_addr + offset))

                    ref_mgr.addMemoryReference(
                        Address(addr + 4),
                        Address(string_table_addr + offset),
                        RefType.DATA,
                        SourceType.USER_DEFINED,
                        0,
                    )
                else:
                    write_bytes(addr + 4, struct.pack("<I", offset))
                    ref_mgr.removeAllReferencesFrom(Address(addr + 4))

        file_idx += 18

    reloc_section_ptr = string_table_addr + string_table_size
    reloc_section_ptr = (reloc_section_ptr + 0xFF) & ~0xFF

    # Map in the relocations for each section
    for section_ptr in range(
        0x14,
        0x14 + (section_no * COFF_SECTION_HEADER_TYPE.getLength()),
        COFF_SECTION_HEADER_TYPE.getLength(),
    ):
        # Get the number of relocs for the section
        reloc_count = struct.unpack(
            "<H", COFF_DATA[section_ptr + 32 : section_ptr + 34]
        )[0]

        # Check if there are relocs for the section
        if reloc_count == 0:
            continue

        # Get the file offset for the reloc table
        reloc_file_offset = struct.unpack(
            "<I", COFF_DATA[section_ptr + 24 : section_ptr + 28]
        )[0]

        # Get the section name
        section_name = "".join(
            [chr(x) for x in COFF_DATA[section_ptr : section_ptr + 8] if x != 0]
        )

        # Set the name of reloc section to .section.reloc
        reloc_name = section_name + ".reloc"

        # Map the relocs for the section
        if memory_map.getBlock(reloc_name) is not None:
            memory_map.removeBlock(memory_map.getBlock(reloc_name), monitor)

        memory_map.createInitializedBlock(
            reloc_name,  # Section name
            Address(reloc_section_ptr),  # Mapping address
            coff_filebytes,  # File backing
            reloc_file_offset,  # File offset
            reloc_count * 10,  # Size
            False,  # Overlay mapping
        )

        # Apply the type to the reloc array
        apply_type(
            reloc_section_ptr,
            ArrayDataType(COFF_RELOC_TYPE, reloc_count, COFF_RELOC_TYPE.getLength()),
        )

        if perform_relocs:
            # Change the `PointerToRelocations` field to reflect the mapped section
            write_bytes(section_ptr + 24, struct.pack("<I", reloc_section_ptr))
            ref_mgr.addMemoryReference(
                Address(section_ptr + 24),
                Address(reloc_section_ptr),
                RefType.DATA,
                SourceType.USER_DEFINED,
                0,
            )
        else:
            write_bytes(section_ptr + 24, struct.pack("<I", 0))
            ref_mgr.removeAllReferencesFrom(Address(section_ptr + 24))

        # Apply the relocations from the reloc table
        apply_section_relocs(
            0x14,
            memory_map.getBlock(section_name),
            memory_map.getBlock(reloc_name).getStart(),
            reloc_count,
            memory_map.getBlock(".symtab").getStart(),
            perform_relocs,
        )

        # Zero out `VirtualAddress` if needed
        if not perform_relocs:
            write_bytes(section_ptr + 12, struct.pack("<I", 0))
            ref_mgr.removeAllReferencesFrom(Address(section_ptr + 12))
            write_bytes(section_ptr + 8, struct.pack("<I", 0))

        reloc_section_ptr += reloc_count * 10
        reloc_section_ptr = (reloc_section_ptr + 0xFF) & ~0xFF


# Entrypoint of the script
if __name__ == "__main__":
    # Check that the current loaded program is a COFF file
    if currentProgram.getExecutableFormat() != "Common Object File Format (COFF)":
        print("Loaded program is not a COFF file")
    else:

        # Prompt the user for whether or not to perform relocations
        try:
            choices = ["Perform relocations", "Add listing view memory references"]

            result = askYesNo(
                "COFF Parser",
                "Perform Relocations and add xrefs?",
            )

            main(result)
        except CancelledException:
            pass
